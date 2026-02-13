"""pipeline/pipeline_core/graph_scorer.py — Generic OSINT Graph Scoring Engine.

A reusable graph-based system for any research pipeline:
- ENTITIES: People, organizations, or any subject found during research
- TARGETS: YouTube channels, websites, profiles linked to entities
- CRITERIA: Configurable scoring rules (not hardcoded)
- SCORES: Weighted multi-criteria scoring with threshold
- TASKS: FIFO queue driving the harvest→pivot→verify loop
- LOGS: Deduplication, no re-scanning

All data persisted in SQLite: RESULTATS/scout_graph.db

Usage example (YouTube cinema Austin):
  graph = GraphScorer()
  graph.configure_criteria([
      {"name": "diplome_confirme", "label": "Diplome confirme", "points": 30},
      {"name": "localisation_bio", "label": "Ville dans la bio", "points": 30},
      {"name": "mots_cles_bio", "label": "Mots-cles forts (Director, DOP...)", "points": 20},
      {"name": "site_personnel", "label": "Lien site externe", "points": 10},
      {"name": "activite_recente", "label": "Video < 6 mois", "points": 10},
  ], threshold=60)
  
  eid = graph.add_entity("John Doe", kind="person", source="UT Austin commencement 2023")
  tid = graph.add_target("https://youtube.com/@johndoe", entity_id=eid, platform="youtube")
  graph.set_criterion(tid, "diplome_confirme", True)
  graph.set_criterion(tid, "localisation_bio", True)
  graph.compute_score(tid)
  # score = 60, validated!

Generic enough for any OSINT: change criteria, entities become companies,
targets become LinkedIn profiles, etc.
"""
import sqlite3
import json
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from config.settings import BASE_DIR


DB_PATH = BASE_DIR / "RESULTATS" / "scout_graph.db"


class GraphScorer:
    """Generic graph-based scoring engine backed by SQLite."""

    def __init__(self, db_path: str = ""):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self):
        with self._conn() as c:
            c.executescript("""
            -- ENTITIES: people, orgs, or any research subject
            CREATE TABLE IF NOT EXISTS entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                kind TEXT DEFAULT 'person',       -- person, organization, place, other
                subkind TEXT DEFAULT '',           -- graduate, instructor, company, etc.
                city TEXT DEFAULT '',
                state TEXT DEFAULT '',
                country TEXT DEFAULT '',
                institution TEXT DEFAULT '',       -- school, company, org
                year INTEGER DEFAULT 0,           -- graduation year, founding year, etc.
                source_url TEXT DEFAULT '',
                source_type TEXT DEFAULT '',       -- commencement_pdf, alumni_page, search_result, manual
                status TEXT DEFAULT 'found',       -- found, target_found, verified, validated, rejected, archived
                metadata TEXT DEFAULT '{}',        -- JSON for extra fields
                created_at REAL DEFAULT 0,
                updated_at REAL DEFAULT 0
            );

            -- TARGETS: YouTube channels, websites, profiles linked to entities
            CREATE TABLE IF NOT EXISTS targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id INTEGER REFERENCES entities(id) ON DELETE CASCADE,
                platform TEXT DEFAULT 'youtube',   -- youtube, vimeo, tiktok, linkedin, website, other
                url TEXT NOT NULL,
                name TEXT DEFAULT '',
                description TEXT DEFAULT '',
                followers INTEGER DEFAULT 0,
                last_activity TEXT DEFAULT '',
                is_active INTEGER DEFAULT 0,       -- boolean: recent activity
                keywords TEXT DEFAULT '[]',        -- JSON array of detected keywords
                location_detected INTEGER DEFAULT 0,
                topic_detected INTEGER DEFAULT 0,
                is_creator INTEGER DEFAULT 0,      -- produces content vs passive
                external_links TEXT DEFAULT '[]',  -- JSON array of external URLs found
                raw_data TEXT DEFAULT '{}',         -- full raw scraped data as JSON
                scanned_at REAL DEFAULT 0,
                UNIQUE(url)
            );

            -- CRITERIA: configurable scoring rules (not hardcoded!)
            CREATE TABLE IF NOT EXISTS criteria (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,          -- machine name: diplome_confirme
                label TEXT DEFAULT '',              -- human label: Diplome confirme
                description TEXT DEFAULT '',
                points INTEGER DEFAULT 0,           -- max points if met
                category TEXT DEFAULT 'default',    -- for grouping in UI
                sort_order INTEGER DEFAULT 0
            );

            -- SCORES: per-target criterion results
            CREATE TABLE IF NOT EXISTS scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id INTEGER REFERENCES targets(id) ON DELETE CASCADE,
                criterion_name TEXT NOT NULL,
                met INTEGER DEFAULT 0,             -- 0=no, 1=yes
                points_awarded INTEGER DEFAULT 0,
                evidence TEXT DEFAULT '',           -- why it was met/not met
                computed_at REAL DEFAULT 0,
                UNIQUE(target_id, criterion_name)
            );

            -- SCORE_TOTALS: cached total per target
            CREATE TABLE IF NOT EXISTS score_totals (
                target_id INTEGER PRIMARY KEY REFERENCES targets(id) ON DELETE CASCADE,
                total INTEGER DEFAULT 0,
                max_possible INTEGER DEFAULT 0,
                validated INTEGER DEFAULT 0,       -- 1 if total >= threshold
                threshold INTEGER DEFAULT 60,
                details TEXT DEFAULT '{}',          -- JSON breakdown
                computed_at REAL DEFAULT 0
            );

            -- TASK_QUEUE: drives the harvest→pivot→verify loop
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,                -- find_names, find_target, analyze_target, verify_location, custom
                target_type TEXT DEFAULT '',        -- what kind of target to find: youtube, linkedin, etc.
                entity_id INTEGER DEFAULT 0,
                target_id INTEGER DEFAULT 0,
                query TEXT DEFAULT '',              -- search query to execute
                status TEXT DEFAULT 'pending',      -- pending, running, done, failed, skipped
                priority INTEGER DEFAULT 5,         -- 1=highest, 10=lowest
                result TEXT DEFAULT '{}',           -- JSON result
                error TEXT DEFAULT '',
                created_at REAL DEFAULT 0,
                started_at REAL DEFAULT 0,
                completed_at REAL DEFAULT 0
            );

            -- LOGS: deduplication
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,               -- searched, scanned, scored, exported
                key TEXT NOT NULL,                  -- dedup key (name, url, query)
                details TEXT DEFAULT '',
                timestamp REAL DEFAULT 0,
                UNIQUE(action, key)
            );

            -- CONFIG: threshold, project name, etc.
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT DEFAULT ''
            );

            -- Indexes
            CREATE INDEX IF NOT EXISTS idx_entities_status ON entities(status);
            CREATE INDEX IF NOT EXISTS idx_entities_city ON entities(city);
            CREATE INDEX IF NOT EXISTS idx_targets_entity ON targets(entity_id);
            CREATE INDEX IF NOT EXISTS idx_targets_platform ON targets(platform);
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority, status);
            CREATE INDEX IF NOT EXISTS idx_logs_key ON logs(action, key);
            """)

    # ══════════════════════════════════════
    # CONFIG
    # ══════════════════════════════════════

    def set_config(self, key: str, value: str):
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO config(key,value) VALUES(?,?)", (key, value))

    def get_config(self, key: str, default: str = "") -> str:
        with self._conn() as c:
            r = c.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
            return r["value"] if r else default

    def configure_criteria(self, criteria: List[Dict], threshold: int = 60):
        """Set up the scoring criteria. Replaces existing criteria.
        
        criteria: [{"name": "diplome", "label": "Diplome confirme", "points": 30}, ...]
        """
        with self._conn() as c:
            c.execute("DELETE FROM criteria")
            for i, cr in enumerate(criteria):
                c.execute("""INSERT INTO criteria(name, label, description, points, category, sort_order)
                    VALUES(?,?,?,?,?,?)""",
                    (cr["name"], cr.get("label", cr["name"]), cr.get("description", ""),
                     cr.get("points", 0), cr.get("category", "default"), i))
            c.execute("INSERT OR REPLACE INTO config(key,value) VALUES('threshold',?)", (str(threshold),))

    def get_criteria(self) -> List[Dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM criteria ORDER BY sort_order").fetchall()
            return [dict(r) for r in rows]

    def get_threshold(self) -> int:
        return int(self.get_config("threshold", "60"))

    # ══════════════════════════════════════
    # ENTITIES
    # ══════════════════════════════════════

    def add_entity(self, name: str, kind: str = "person", **kwargs) -> int:
        """Add an entity (person, org, etc). Returns entity ID."""
        now = time.time()
        with self._conn() as c:
            # Dedup by name + city
            existing = c.execute(
                "SELECT id FROM entities WHERE name=? AND city=?",
                (name, kwargs.get("city", ""))).fetchone()
            if existing:
                return existing["id"]
            
            r = c.execute("""INSERT INTO entities(name, kind, subkind, city, state, country,
                institution, year, source_url, source_type, status, metadata, created_at, updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (name, kind, kwargs.get("subkind", ""), kwargs.get("city", ""),
                 kwargs.get("state", ""), kwargs.get("country", ""),
                 kwargs.get("institution", ""), kwargs.get("year", 0),
                 kwargs.get("source_url", ""), kwargs.get("source_type", ""),
                 kwargs.get("status", "found"),
                 json.dumps(kwargs.get("metadata", {})), now, now))
            return r.lastrowid

    def update_entity(self, entity_id: int, **kwargs):
        with self._conn() as c:
            sets = []
            vals = []
            for k, v in kwargs.items():
                if k in ("name","kind","subkind","city","state","country","institution",
                         "year","source_url","source_type","status","metadata"):
                    sets.append(f"{k}=?")
                    vals.append(json.dumps(v) if k == "metadata" else v)
            if sets:
                sets.append("updated_at=?")
                vals.append(time.time())
                vals.append(entity_id)
                c.execute(f"UPDATE entities SET {','.join(sets)} WHERE id=?", vals)

    def get_entity(self, entity_id: int) -> Optional[Dict]:
        with self._conn() as c:
            r = c.execute("SELECT * FROM entities WHERE id=?", (entity_id,)).fetchone()
            return dict(r) if r else None

    def find_entities(self, status: str = "", city: str = "", kind: str = "",
                      limit: int = 500) -> List[Dict]:
        with self._conn() as c:
            where, params = [], []
            if status: where.append("status=?"); params.append(status)
            if city: where.append("city=?"); params.append(city)
            if kind: where.append("kind=?"); params.append(kind)
            sql = "SELECT * FROM entities"
            if where: sql += " WHERE " + " AND ".join(where)
            sql += f" ORDER BY created_at DESC LIMIT {limit}"
            return [dict(r) for r in c.execute(sql, params).fetchall()]

    def count_entities(self, status: str = "") -> int:
        with self._conn() as c:
            if status:
                return c.execute("SELECT COUNT(*) FROM entities WHERE status=?", (status,)).fetchone()[0]
            return c.execute("SELECT COUNT(*) FROM entities").fetchone()[0]

    # ══════════════════════════════════════
    # TARGETS
    # ══════════════════════════════════════

    def add_target(self, url: str, entity_id: int = 0, platform: str = "youtube",
                   **kwargs) -> int:
        """Add a target (channel, profile, website). Returns target ID."""
        with self._conn() as c:
            existing = c.execute("SELECT id FROM targets WHERE url=?", (url,)).fetchone()
            if existing:
                # Link to entity if not already linked
                if entity_id:
                    c.execute("UPDATE targets SET entity_id=? WHERE id=? AND entity_id=0",
                              (entity_id, existing["id"]))
                return existing["id"]
            
            r = c.execute("""INSERT INTO targets(entity_id, platform, url, name, description,
                followers, last_activity, is_active, keywords, location_detected, topic_detected,
                is_creator, external_links, raw_data, scanned_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (entity_id, platform, url,
                 kwargs.get("name", ""), kwargs.get("description", ""),
                 kwargs.get("followers", 0), kwargs.get("last_activity", ""),
                 int(kwargs.get("is_active", False)),
                 json.dumps(kwargs.get("keywords", [])),
                 int(kwargs.get("location_detected", False)),
                 int(kwargs.get("topic_detected", False)),
                 int(kwargs.get("is_creator", False)),
                 json.dumps(kwargs.get("external_links", [])),
                 json.dumps(kwargs.get("raw_data", {})),
                 time.time()))
            return r.lastrowid

    def update_target(self, target_id: int, **kwargs):
        with self._conn() as c:
            sets, vals = [], []
            for k, v in kwargs.items():
                if k in ("name","description","followers","last_activity","is_active",
                         "keywords","location_detected","topic_detected","is_creator",
                         "external_links","raw_data","entity_id","platform"):
                    sets.append(f"{k}=?")
                    if k in ("keywords","external_links","raw_data"):
                        vals.append(json.dumps(v))
                    elif k in ("is_active","location_detected","topic_detected","is_creator"):
                        vals.append(int(v))
                    else:
                        vals.append(v)
            if sets:
                sets.append("scanned_at=?"); vals.append(time.time())
                vals.append(target_id)
                c.execute(f"UPDATE targets SET {','.join(sets)} WHERE id=?", vals)

    def get_target(self, target_id: int) -> Optional[Dict]:
        with self._conn() as c:
            r = c.execute("SELECT * FROM targets WHERE id=?", (target_id,)).fetchone()
            if not r: return None
            d = dict(r)
            d["keywords"] = json.loads(d.get("keywords","[]"))
            d["external_links"] = json.loads(d.get("external_links","[]"))
            return d

    def get_targets_for_entity(self, entity_id: int) -> List[Dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM targets WHERE entity_id=? ORDER BY scanned_at DESC",
                             (entity_id,)).fetchall()
            return [dict(r) for r in rows]

    def find_targets(self, platform: str = "", validated: Optional[bool] = None,
                     min_score: int = 0, limit: int = 500) -> List[Dict]:
        """Find targets with optional filtering by score validation."""
        with self._conn() as c:
            sql = """SELECT t.*, st.total as score_total, st.validated as score_validated,
                     e.name as entity_name, e.city as entity_city, e.institution as entity_institution
                     FROM targets t
                     LEFT JOIN score_totals st ON st.target_id = t.id
                     LEFT JOIN entities e ON e.id = t.entity_id"""
            where, params = [], []
            if platform: where.append("t.platform=?"); params.append(platform)
            if validated is not None: where.append("st.validated=?"); params.append(int(validated))
            if min_score: where.append("COALESCE(st.total,0)>=?"); params.append(min_score)
            if where: sql += " WHERE " + " AND ".join(where)
            sql += f" ORDER BY COALESCE(st.total,0) DESC LIMIT {limit}"
            return [dict(r) for r in c.execute(sql, params).fetchall()]

    # ══════════════════════════════════════
    # SCORING
    # ══════════════════════════════════════

    def set_criterion(self, target_id: int, criterion_name: str, met: bool,
                      evidence: str = ""):
        """Set whether a criterion is met for a target."""
        with self._conn() as c:
            cr = c.execute("SELECT points FROM criteria WHERE name=?", (criterion_name,)).fetchone()
            pts = cr["points"] if cr and met else 0
            c.execute("""INSERT OR REPLACE INTO scores(target_id, criterion_name, met, points_awarded,
                evidence, computed_at) VALUES(?,?,?,?,?,?)""",
                (target_id, criterion_name, int(met), pts, evidence, time.time()))

    def compute_score(self, target_id: int) -> Dict:
        """Compute total score for a target based on all criteria."""
        with self._conn() as c:
            criteria = c.execute("SELECT * FROM criteria ORDER BY sort_order").fetchall()
            threshold = int(self.get_config("threshold", "60"))
            
            total = 0
            max_possible = 0
            details = {}
            
            for cr in criteria:
                max_possible += cr["points"]
                sc = c.execute("SELECT * FROM scores WHERE target_id=? AND criterion_name=?",
                               (target_id, cr["name"])).fetchone()
                awarded = sc["points_awarded"] if sc else 0
                met = bool(sc["met"]) if sc else False
                total += awarded
                details[cr["name"]] = {
                    "label": cr["label"],
                    "max": cr["points"],
                    "awarded": awarded,
                    "met": met,
                    "evidence": sc["evidence"] if sc else "",
                }
            
            validated = total >= threshold
            
            c.execute("""INSERT OR REPLACE INTO score_totals(target_id, total, max_possible,
                validated, threshold, details, computed_at) VALUES(?,?,?,?,?,?,?)""",
                (target_id, total, max_possible, int(validated),
                 threshold, json.dumps(details), time.time()))
            
            # Update entity status
            t = c.execute("SELECT entity_id FROM targets WHERE id=?", (target_id,)).fetchone()
            if t and t["entity_id"]:
                new_status = "validated" if validated else "scored"
                c.execute("UPDATE entities SET status=?, updated_at=? WHERE id=?",
                          (new_status, time.time(), t["entity_id"]))
            
            return {"target_id": target_id, "total": total, "max_possible": max_possible,
                    "validated": validated, "threshold": threshold, "details": details}

    def get_score(self, target_id: int) -> Optional[Dict]:
        with self._conn() as c:
            r = c.execute("SELECT * FROM score_totals WHERE target_id=?", (target_id,)).fetchone()
            if not r: return None
            d = dict(r)
            d["details"] = json.loads(d.get("details","{}"))
            return d

    def compute_all_scores(self) -> Dict:
        """Recompute scores for all targets. Returns summary."""
        with self._conn() as c:
            targets = c.execute("SELECT id FROM targets").fetchall()
            total = len(targets)
            validated = 0
            for t in targets:
                result = self.compute_score(t["id"])
                if result["validated"]:
                    validated += 1
            return {"total_targets": total, "validated": validated, "rejected": total - validated}

    # ══════════════════════════════════════
    # TASK QUEUE
    # ══════════════════════════════════════

    def add_task(self, task_type: str, entity_id: int = 0, target_id: int = 0,
                 query: str = "", priority: int = 5, target_type: str = "") -> int:
        """Add a task to the queue."""
        with self._conn() as c:
            # Dedup: don't add same task twice
            existing = c.execute(
                "SELECT id FROM tasks WHERE type=? AND entity_id=? AND target_id=? AND status IN ('pending','running')",
                (task_type, entity_id, target_id)).fetchone()
            if existing:
                return existing["id"]
            
            r = c.execute("""INSERT INTO tasks(type, target_type, entity_id, target_id, query,
                status, priority, created_at) VALUES(?,?,?,?,?,?,?,?)""",
                (task_type, target_type, entity_id, target_id, query, "pending", priority, time.time()))
            return r.lastrowid

    def get_next_task(self) -> Optional[Dict]:
        """Get next pending task (highest priority first)."""
        with self._conn() as c:
            r = c.execute("""SELECT * FROM tasks WHERE status='pending'
                ORDER BY priority ASC, created_at ASC LIMIT 1""").fetchone()
            if not r: return None
            c.execute("UPDATE tasks SET status='running', started_at=? WHERE id=?",
                      (time.time(), r["id"]))
            return dict(r)

    def complete_task(self, task_id: int, result: Dict = None, error: str = ""):
        with self._conn() as c:
            status = "failed" if error else "done"
            c.execute("UPDATE tasks SET status=?, result=?, error=?, completed_at=? WHERE id=?",
                      (status, json.dumps(result or {}), error, time.time(), task_id))

    def count_tasks(self, status: str = "pending") -> int:
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) FROM tasks WHERE status=?", (status,)).fetchone()[0]

    def get_tasks(self, status: str = "", limit: int = 100) -> List[Dict]:
        with self._conn() as c:
            if status:
                rows = c.execute("SELECT * FROM tasks WHERE status=? ORDER BY created_at DESC LIMIT ?",
                                 (status, limit)).fetchall()
            else:
                rows = c.execute("SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
                                 (limit,)).fetchall()
            return [dict(r) for r in rows]

    # ══════════════════════════════════════
    # LOGS (deduplication)
    # ══════════════════════════════════════

    def was_done(self, action: str, key: str) -> bool:
        """Check if an action was already done (for dedup)."""
        with self._conn() as c:
            return c.execute("SELECT 1 FROM logs WHERE action=? AND key=?",
                             (action, key)).fetchone() is not None

    def mark_done(self, action: str, key: str, details: str = ""):
        with self._conn() as c:
            c.execute("INSERT OR IGNORE INTO logs(action, key, details, timestamp) VALUES(?,?,?,?)",
                      (action, key, details, time.time()))

    # ══════════════════════════════════════
    # STATISTICS & EXPORT
    # ══════════════════════════════════════

    def get_stats(self) -> Dict:
        """Get overall statistics for UI display."""
        with self._conn() as c:
            stats = {
                "entities": {
                    "total": c.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
                    "by_status": {},
                },
                "targets": {
                    "total": c.execute("SELECT COUNT(*) FROM targets").fetchone()[0],
                    "by_platform": {},
                },
                "scores": {
                    "validated": c.execute("SELECT COUNT(*) FROM score_totals WHERE validated=1").fetchone()[0],
                    "rejected": c.execute("SELECT COUNT(*) FROM score_totals WHERE validated=0").fetchone()[0],
                    "unscored": 0,
                    "avg_score": 0,
                },
                "tasks": {
                    "pending": c.execute("SELECT COUNT(*) FROM tasks WHERE status='pending'").fetchone()[0],
                    "running": c.execute("SELECT COUNT(*) FROM tasks WHERE status='running'").fetchone()[0],
                    "done": c.execute("SELECT COUNT(*) FROM tasks WHERE status='done'").fetchone()[0],
                    "failed": c.execute("SELECT COUNT(*) FROM tasks WHERE status='failed'").fetchone()[0],
                },
                "criteria": self.get_criteria(),
                "threshold": self.get_threshold(),
            }
            # By status
            for r in c.execute("SELECT status, COUNT(*) as cnt FROM entities GROUP BY status").fetchall():
                stats["entities"]["by_status"][r["status"]] = r["cnt"]
            # By platform
            for r in c.execute("SELECT platform, COUNT(*) as cnt FROM targets GROUP BY platform").fetchall():
                stats["targets"]["by_platform"][r["platform"]] = r["cnt"]
            # Avg score
            avg = c.execute("SELECT AVG(total) FROM score_totals").fetchone()[0]
            stats["scores"]["avg_score"] = round(avg, 1) if avg else 0
            scored_count = stats["scores"]["validated"] + stats["scores"]["rejected"]
            stats["scores"]["unscored"] = stats["targets"]["total"] - scored_count
            
            return stats

    def export_validated(self) -> List[Dict]:
        """Export all validated targets with full details for CSV/JSON."""
        with self._conn() as c:
            rows = c.execute("""
                SELECT t.*, e.name as entity_name, e.kind as entity_kind,
                       e.institution, e.year, e.city, e.state,
                       st.total as score, st.max_possible, st.details as score_details
                FROM targets t
                JOIN score_totals st ON st.target_id = t.id
                LEFT JOIN entities e ON e.id = t.entity_id
                WHERE st.validated = 1
                ORDER BY st.total DESC
            """).fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["score_details"] = json.loads(d.get("score_details","{}"))
                d["keywords"] = json.loads(d.get("keywords","[]"))
                results.append(d)
            return results

    def export_all(self) -> List[Dict]:
        """Export ALL targets (validated + rejected) with scores."""
        with self._conn() as c:
            rows = c.execute("""
                SELECT t.*, e.name as entity_name, e.kind as entity_kind,
                       e.institution, e.year, e.city, e.state,
                       COALESCE(st.total, 0) as score,
                       COALESCE(st.max_possible, 0) as max_possible,
                       COALESCE(st.validated, 0) as validated,
                       COALESCE(st.details, '{}') as score_details
                FROM targets t
                LEFT JOIN score_totals st ON st.target_id = t.id
                LEFT JOIN entities e ON e.id = t.entity_id
                ORDER BY COALESCE(st.total, 0) DESC
            """).fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["score_details"] = json.loads(d.get("score_details","{}"))
                d["keywords"] = json.loads(d.get("keywords","[]"))
                results.append(d)
            return results

    def reset(self):
        """Clear all data (for testing)."""
        with self._conn() as c:
            for table in ["scores","score_totals","tasks","logs","targets","entities"]:
                c.execute(f"DELETE FROM {table}")
