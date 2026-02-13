"""pipeline/pipeline_core/cost_engine.py — Smart search cost/value optimizer.

Implements 3 mathematical optimization strategies:

1. COST/VALUE FUNCTION (ROI)
   Score = Probability(Success) / Cost(Time + Risk)
   Each action gets a score BEFORE execution. Low ROI → skip.

2. PATIENCE BUDGET (Diminishing Returns)
   Budget starts at N. Find something useful → recharge (+K).
   Scrape useless page → drain (-1). Budget=0 → stop this branch.

3. EPSILON-GREEDY (Multi-Armed Bandit)
   90% of the time: exploit the best-performing source.
   10% of the time: explore a random new source.
   If the new source performs better, it becomes the new priority.

Generic: works for any research — YouTubers, companies, people, etc.
The module doesn't do scraping itself — it DECIDES what to scrape next
and when to stop.

Usage:
    engine = CostEngine(target_count=10, patience=30)
    engine.add_source("university_alumni", priority=100)
    engine.add_source("local_press", priority=50)
    engine.add_source("reddit", priority=30)
    
    while not engine.should_stop():
        source, query = engine.next_action()
        results = do_search(query)  # your scraping code
        engine.report_result(source, found=len(results), cost=1)
    
    print(engine.summary())
"""
import time
import json
import random
import math
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field, asdict


# ══════════════════════════════════════
# DATA STRUCTURES
# ══════════════════════════════════════

@dataclass
class SourceStats:
    """Tracks performance of a single research source/branch."""
    name: str
    priority: float = 50.0          # Initial priority (0-100)
    attempts: int = 0               # Total pages/queries tried
    hits: int = 0                   # Useful results found
    misses: int = 0                 # Useless pages scraped
    total_cost: float = 0.0         # Accumulated cost (time, tokens, etc.)
    total_value: float = 0.0        # Accumulated value from findings
    patience: int = 0               # Current patience for this source
    exhausted: bool = False         # True if patience reached 0
    last_hit_at: int = 0            # Attempt number of last hit
    created_at: float = 0.0
    
    @property
    def hit_rate(self) -> float:
        """Success rate: hits / attempts."""
        return self.hits / max(1, self.attempts)
    
    @property
    def roi(self) -> float:
        """Return on investment: value / cost."""
        return self.total_value / max(0.01, self.total_cost)
    
    @property
    def drought(self) -> int:
        """How many attempts since last hit."""
        return self.attempts - self.last_hit_at
    
    @property
    def effective_priority(self) -> float:
        """Dynamic priority based on performance.
        High hit rate → higher priority.
        Long drought → lower priority.
        """
        if self.exhausted:
            return 0.0
        if self.attempts == 0:
            return self.priority  # No data yet, use initial
        
        # Base: initial priority weighted down over time
        base = self.priority * 0.3
        # Performance: hit rate heavily weighted
        perf = self.hit_rate * 100 * 0.5
        # Recency: penalize long droughts
        recency_penalty = min(30, self.drought * 1.5)
        # ROI bonus
        roi_bonus = min(20, self.roi * 5)
        
        return max(0, base + perf - recency_penalty + roi_bonus)
    
    def to_dict(self) -> Dict:
        d = asdict(self)
        d["hit_rate"] = round(self.hit_rate, 3)
        d["roi"] = round(self.roi, 3)
        d["drought"] = self.drought
        d["effective_priority"] = round(self.effective_priority, 1)
        return d


@dataclass
class ActionLog:
    """Single action record for analysis."""
    source: str
    query: str = ""
    found: int = 0
    cost: float = 1.0
    value: float = 0.0
    roi_predicted: float = 0.0
    decision: str = ""  # "execute", "skip", "explore"
    timestamp: float = 0.0


# ══════════════════════════════════════
# COST ENGINE
# ══════════════════════════════════════

class CostEngine:
    """Smart search optimizer that decides WHAT to scrape and WHEN to stop.
    
    Args:
        target_count: Stop when this many validated results are found.
        patience_initial: Starting patience budget per source.
        patience_recharge: How much patience to add on a hit.
        patience_drain: How much patience to remove on a miss.
        epsilon: Exploration rate (0.0 = pure exploit, 1.0 = pure random).
        min_roi: Minimum ROI threshold to execute an action.
        global_budget: Maximum total actions across all sources.
    """
    
    def __init__(self,
                 target_count: int = 10,
                 patience_initial: int = 30,
                 patience_recharge: int = 20,
                 patience_drain: int = 1,
                 epsilon: float = 0.10,
                 min_roi: float = 0.05,
                 global_budget: int = 500):
        
        self.target_count = target_count
        self.patience_initial = patience_initial
        self.patience_recharge = patience_recharge
        self.patience_drain = patience_drain
        self.epsilon = epsilon
        self.min_roi = min_roi
        self.global_budget = global_budget
        
        # State
        self.sources: Dict[str, SourceStats] = {}
        self.total_found: int = 0
        self.total_actions: int = 0
        self.action_log: List[ActionLog] = []
        self.started_at: float = time.time()
        self._stopped: bool = False
        self._stop_reason: str = ""
    
    # ── Source Management ──
    
    def add_source(self, name: str, priority: float = 50.0):
        """Register a research source/branch."""
        if name not in self.sources:
            self.sources[name] = SourceStats(
                name=name,
                priority=priority,
                patience=self.patience_initial,
                created_at=time.time()
            )
    
    def get_source(self, name: str) -> Optional[SourceStats]:
        return self.sources.get(name)
    
    # ── Cost/Value Prediction ──
    
    def predict_roi(self, source_name: str, estimated_cost: float = 1.0) -> float:
        """Predict ROI for the next action on this source.
        
        Score = P(success) / Cost
        P(success) is estimated from historical hit rate + prior.
        """
        src = self.sources.get(source_name)
        if not src:
            return 0.0
        
        if src.exhausted:
            return 0.0
        
        # Bayesian estimate of success probability
        # Prior: initial priority / 100
        # Evidence: observed hit rate
        prior = src.priority / 100.0
        if src.attempts == 0:
            p_success = prior
        else:
            # Weight prior less as we get more data
            alpha = min(1.0, src.attempts / 10.0)
            p_success = (1 - alpha) * prior + alpha * src.hit_rate
        
        # Diminishing returns: success probability decays with drought
        drought_decay = math.exp(-0.05 * src.drought)
        p_adjusted = p_success * drought_decay
        
        # ROI = probability / cost
        return p_adjusted / max(0.01, estimated_cost)
    
    # ── Decision: Should we continue? ──
    
    def should_stop(self) -> bool:
        """Global stop condition. Returns True if we should stop ALL searching."""
        if self._stopped:
            return True
        
        # Target reached
        if self.total_found >= self.target_count:
            self._stop("target_reached",
                        f"Found {self.total_found}/{self.target_count} targets")
            return True
        
        # Global budget exhausted
        if self.total_actions >= self.global_budget:
            self._stop("budget_exhausted",
                        f"Used {self.total_actions}/{self.global_budget} actions")
            return True
        
        # All sources exhausted
        active = [s for s in self.sources.values() if not s.exhausted]
        if not active and self.sources:
            self._stop("all_sources_exhausted",
                        f"All {len(self.sources)} sources exhausted")
            return True
        
        return False
    
    def _stop(self, reason: str, detail: str = ""):
        self._stopped = True
        self._stop_reason = f"{reason}: {detail}"
    
    def force_stop(self):
        self._stop("manual", "Stopped by user")
    
    # ── Decision: What to do next? (Epsilon-Greedy) ──
    
    def next_source(self) -> Optional[str]:
        """Pick the next source to query using epsilon-greedy strategy.
        
        Returns source name, or None if all exhausted.
        """
        active = [s for s in self.sources.values() if not s.exhausted]
        if not active:
            return None
        
        # Epsilon-greedy: explore vs exploit
        if random.random() < self.epsilon and len(active) > 1:
            # EXPLORE: pick a random source (not the best one)
            best = max(active, key=lambda s: s.effective_priority)
            others = [s for s in active if s.name != best.name]
            if others:
                chosen = random.choice(others)
                return chosen.name
        
        # EXPLOIT: pick the source with highest effective priority
        best = max(active, key=lambda s: s.effective_priority)
        
        # Check minimum ROI before committing
        roi = self.predict_roi(best.name)
        if roi < self.min_roi and best.attempts > 5:
            # Even the best source is below minimum ROI
            # Mark it exhausted and try again
            best.exhausted = True
            return self.next_source()  # Recursive: try next best
        
        return best.name
    
    # ── Report results (feedback loop) ──
    
    def report_result(self, source_name: str, found: int = 0, cost: float = 1.0,
                      value: float = 0.0, query: str = ""):
        """Report the outcome of a scraping action.
        
        Args:
            source_name: Which source was queried.
            found: Number of useful results found (0 = miss).
            cost: Cost of this action (time, tokens, etc).
            value: Value of findings (can be score-based).
            query: The query string used (for logging).
        """
        src = self.sources.get(source_name)
        if not src:
            return
        
        # If no explicit value, default: each find = 10 value points
        if found > 0 and value == 0:
            value = found * 10.0
        
        src.attempts += 1
        src.total_cost += cost
        self.total_actions += 1
        
        if found > 0:
            # HIT: recharge patience, update stats
            src.hits += found
            src.total_value += value
            src.patience = min(
                self.patience_initial * 2,  # Cap at 2x initial
                src.patience + self.patience_recharge
            )
            src.last_hit_at = src.attempts
            self.total_found += found
            decision = "hit"
        else:
            # MISS: drain patience
            src.misses += 1
            src.patience -= self.patience_drain
            decision = "miss"
            
            # Check if source is exhausted
            if src.patience <= 0:
                src.exhausted = True
                src.patience = 0
                decision = "exhausted"
        
        # Log
        roi = self.predict_roi(source_name, cost)
        self.action_log.append(ActionLog(
            source=source_name, query=query, found=found,
            cost=cost, value=value, roi_predicted=roi,
            decision=decision, timestamp=time.time()
        ))
    
    # ── Priority Queue: rank all pending actions ──
    
    def rank_sources(self) -> List[Dict]:
        """Return all sources ranked by effective priority.
        Useful for UI display."""
        ranked = sorted(self.sources.values(),
                       key=lambda s: s.effective_priority, reverse=True)
        return [s.to_dict() for s in ranked]
    
    # ── Batch evaluation: should we scrape this URL? ──
    
    def evaluate_action(self, source_name: str, estimated_cost: float = 1.0) -> Dict:
        """Evaluate whether a specific action is worth doing.
        
        Returns:
            {"execute": bool, "roi": float, "reason": str, "source_patience": int}
        """
        src = self.sources.get(source_name)
        if not src:
            return {"execute": False, "roi": 0, "reason": "unknown_source",
                    "source_patience": 0}
        
        if src.exhausted:
            return {"execute": False, "roi": 0, "reason": "source_exhausted",
                    "source_patience": 0}
        
        if self.should_stop():
            return {"execute": False, "roi": 0, "reason": self._stop_reason,
                    "source_patience": src.patience}
        
        roi = self.predict_roi(source_name, estimated_cost)
        
        if roi < self.min_roi and src.attempts > 5:
            return {"execute": False, "roi": round(roi, 4),
                    "reason": f"ROI too low ({roi:.4f} < {self.min_roi})",
                    "source_patience": src.patience}
        
        return {"execute": True, "roi": round(roi, 4),
                "reason": "go", "source_patience": src.patience}
    
    # ── Statistics & Summary ──
    
    def summary(self) -> Dict:
        """Full summary for UI display and logging."""
        elapsed = time.time() - self.started_at
        
        return {
            "status": "stopped" if self._stopped else "running",
            "stop_reason": self._stop_reason,
            "elapsed_seconds": round(elapsed, 1),
            "total_found": self.total_found,
            "target_count": self.target_count,
            "progress_pct": round(self.total_found / max(1, self.target_count) * 100, 1),
            "total_actions": self.total_actions,
            "global_budget": self.global_budget,
            "budget_used_pct": round(self.total_actions / max(1, self.global_budget) * 100, 1),
            "efficiency": round(self.total_found / max(1, self.total_actions), 4),
            "sources": self.rank_sources(),
            "active_sources": len([s for s in self.sources.values() if not s.exhausted]),
            "exhausted_sources": len([s for s in self.sources.values() if s.exhausted]),
        }
    
    def get_log(self, last_n: int = 50) -> List[Dict]:
        """Return recent action log entries."""
        entries = self.action_log[-last_n:]
        return [asdict(a) for a in entries]
    
    def get_efficiency_curve(self) -> List[Dict]:
        """Returns cumulative efficiency over time for charting.
        
        Each point: {"action": N, "found": cumulative, "efficiency": found/action}
        Useful for plotting diminishing returns.
        """
        curve = []
        cumulative = 0
        for i, log in enumerate(self.action_log):
            cumulative += log.found
            curve.append({
                "action": i + 1,
                "found": cumulative,
                "efficiency": round(cumulative / (i + 1), 4),
                "source": log.source,
                "decision": log.decision,
            })
        return curve
    
    # ── Serialization ──
    
    def to_dict(self) -> Dict:
        """Full state as dict (for saving/restoring)."""
        return {
            "config": {
                "target_count": self.target_count,
                "patience_initial": self.patience_initial,
                "patience_recharge": self.patience_recharge,
                "patience_drain": self.patience_drain,
                "epsilon": self.epsilon,
                "min_roi": self.min_roi,
                "global_budget": self.global_budget,
            },
            "state": {
                "total_found": self.total_found,
                "total_actions": self.total_actions,
                "stopped": self._stopped,
                "stop_reason": self._stop_reason,
                "started_at": self.started_at,
            },
            "sources": {k: v.to_dict() for k, v in self.sources.items()},
            "summary": self.summary(),
        }
    
    def save(self, path: str = ""):
        """Save state to JSON file."""
        p = Path(path) if path else (Path(BASE_DIR) / "RESULTATS" / "cost_engine_state.json")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    
    @classmethod
    def load(cls, path: str = "") -> "CostEngine":
        """Load state from JSON file."""
        from config.settings import BASE_DIR
        p = Path(path) if path else (Path(BASE_DIR) / "RESULTATS" / "cost_engine_state.json")
        if not p.exists():
            return cls()
        data = json.loads(p.read_text(encoding="utf-8"))
        cfg = data.get("config", {})
        engine = cls(**cfg)
        state = data.get("state", {})
        engine.total_found = state.get("total_found", 0)
        engine.total_actions = state.get("total_actions", 0)
        engine._stopped = state.get("stopped", False)
        engine._stop_reason = state.get("stop_reason", "")
        engine.started_at = state.get("started_at", time.time())
        for name, sd in data.get("sources", {}).items():
            src = SourceStats(
                name=name, priority=sd.get("priority", 50),
                attempts=sd.get("attempts", 0), hits=sd.get("hits", 0),
                misses=sd.get("misses", 0), total_cost=sd.get("total_cost", 0),
                total_value=sd.get("total_value", 0), patience=sd.get("patience", 0),
                exhausted=sd.get("exhausted", False), last_hit_at=sd.get("last_hit_at", 0),
                created_at=sd.get("created_at", 0))
            engine.sources[name] = src
        return engine
