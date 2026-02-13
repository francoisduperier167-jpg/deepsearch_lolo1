"""pipeline/pipeline.py — Main orchestrator (v3).

Integrates all modules:
- StrategyPlanner: decomposes prompt → strategies → queries
- CostEngine: decides WHAT to scrape and WHEN to stop
- GraphScorer: stores entities, targets, scores in SQLite
- Checkpoints: pauses for user validation at key points
- Persistence: saves state to disk, can resume after crash

Flow per city:
  1. Load queries from StrategyPlanner (or fallback to query_generator)
  2. CHECKPOINT: validate queries
  3. Browser navigation → HTML saved + parsed → results
  4. CostEngine: report hit/miss, check patience
  5. CHECKPOINT: review search results
  6. Triage + extract fragments → assemble candidates
  7. Feed candidates into GraphScorer as entities + targets
  8. CHECKPOINT: review candidates
  9. YouTube verification → graph scoring → CSV export
"""
import asyncio
import json
import re as _re
import time
import random
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path
import aiohttp

from config.settings import (BASE_DIR, MODELS, MAX_WAVES, PAGES_PER_QUERY, MAX_PAGES_TO_FETCH,
    MIN_TRIAGE_SCORE, MIN_CITY_SCORE, MIN_TOTAL_SCORE, RESOLVED, FAILED, PARTIAL, IN_PROGRESS, PENDING)
from config.cities import US_STATES_CITIES, CATEGORIES, CATEGORY_LABELS
from models.data_models import (Fragment, ChannelCandidate, CategoryResolution,
    CityResolution, StateResolution)
from server.server_core.state import app_state
from server.server_core.llm_client import query_llm
from utils.logger import logger
from pipeline.pipeline_ui.progress import progress_callback
from pipeline.pipeline_core.query_generator import generate_queries
from pipeline.pipeline_core.result_triage import triage_results
from pipeline.pipeline_core.page_extractor import extract_fragments
from pipeline.pipeline_core.candidate_assembler import assemble_candidates
from pipeline.pipeline_core.followup_search import run_followups
from pipeline.pipeline_core.verification import verify_city, verify_category
from pipeline.pipeline_core.escalation import analyze_failure
from pipeline.pipeline_core.csv_saver import save_search_csv, save_verified_csv
from web_search.web_search_core.html_parser import parse_search_html, save_parsed_csv
from web_search.web_search import fetch_page, verify_youtube_channel

# New modules
from pipeline.pipeline_core.graph_scorer import GraphScorer
from pipeline.pipeline_core.cost_engine import CostEngine
from pipeline.pipeline_core.strategy_planner import StrategyPlanner


# ══════════════════════════════════════
# CHECKPOINT
# ══════════════════════════════════════

async def checkpoint(name: str, data: dict) -> str:
    """Pause pipeline for user validation. Returns "continue"|"modify"|"skip"."""
    if app_state.auto_mode:
        return "continue"

    logger.log(f"  ✋ CHECKPOINT [{name}] — En attente de validation...")

    # Persist checkpoint to disk for crash recovery
    _save_checkpoint(name, data)

    app_state.checkpoint_name = name
    app_state.checkpoint_data = data
    app_state.checkpoint_waiting = True
    app_state.checkpoint_response = None
    app_state.checkpoint_modifications = {}
    app_state.checkpoint_event = asyncio.Event()

    while not app_state.checkpoint_event.is_set():
        if not app_state.scan_running:
            return "skip"
        await asyncio.sleep(0.3)

    response = app_state.checkpoint_response or "continue"
    app_state.checkpoint_waiting = False
    app_state.checkpoint_name = ""
    _clear_checkpoint()
    return response


def _save_checkpoint(name, data):
    p = BASE_DIR / "RESULTATS" / "_checkpoint.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"name": name, "data": data, "time": time.time()},
                            ensure_ascii=False, default=str), encoding="utf-8")

def _clear_checkpoint():
    p = BASE_DIR / "RESULTATS" / "_checkpoint.json"
    if p.exists():
        p.unlink()


# ══════════════════════════════════════
# HELPERS
# ══════════════════════════════════════

def _safe(text: str, maxlen: int = 40) -> str:
    """Safe folder/file name."""
    return _re.sub(r'[^a-zA-Z0-9_-]', '', text.replace(' ', '_'))[:maxlen]


def _load_plan_queries(city: str, state: str, cat_label: str, wave: int) -> Optional[List[Dict]]:
    """Try to load queries from saved StrategyPlanner plan."""
    plan_path = BASE_DIR / "RESULTATS" / "strategy_plan.json"
    if not plan_path.exists():
        return None
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        strategies = plan.get("strategies", [])
        if not strategies:
            return None

        # Pick strategy tier based on wave
        tier_idx = min(wave - 1, len(strategies) - 1)
        strat = strategies[tier_idx]

        queries = []
        for step in strat.get("steps", []):
            for q in step.get("queries", []):
                filled = q.replace("{city}", city).replace("{state}", state).replace("{country}", "USA")
                queries.append({"query": filled, "angle": step.get("action", ""),
                                "step_id": step.get("id", ""), "source_type": step.get("source_type", "")})
            # Also recurse into sub_steps
            for sub in step.get("sub_steps", []):
                for q in sub.get("queries", []):
                    filled = q.replace("{city}", city).replace("{state}", state).replace("{country}", "USA")
                    queries.append({"query": filled, "angle": sub.get("action", ""),
                                    "step_id": sub.get("id", ""), "source_type": sub.get("source_type", "")})
        return queries if queries else None
    except Exception as e:
        logger.log(f"  [PLAN] Error loading: {str(e)[:80]}")
        return None


# ══════════════════════════════════════
# PIPELINE ORCHESTRATOR
# ══════════════════════════════════════

class PipelineOrchestrator:
    def __init__(self):
        self.running = True
        self.states: Dict[str, StateResolution] = {}
        self.graph = GraphScorer()
        self.cost = CostEngine(
            target_count=int(app_state.progress.get("total_tasks", 450)),
            patience_initial=30,
            patience_recharge=20,
            global_budget=5000,
        )
        # Register source tiers for CostEngine
        self.cost.add_source("direct", priority=90)
        self.cost.add_source("semi_direct", priority=60)
        self.cost.add_source("indirect", priority=40)

    def stop(self):
        self.running = False

    # ── State loop ──

    async def process_state(self, state_name: str, cities: List[str]) -> StateResolution:
        logger.log(f"\n{'='*60}\nSTATE: {state_name}\n{'='*60}")
        sr = StateResolution(state=state_name, status=IN_PROGRESS)
        for c in cities:
            cr = CityResolution(city=c, state=state_name, status=PENDING)
            for cat in CATEGORIES:
                cr.categories[cat] = CategoryResolution(category=cat)
            sr.cities[c] = cr
        for city_name in cities:
            if not self.running:
                break
            await self._process_city(sr.cities[city_name], state_name)
            progress_callback({"type": "state_progress", "state": state_name, "summary": sr.summary()})
        sr.status = RESOLVED if sr.is_resolved() else PARTIAL
        self.states[state_name] = sr
        logger.log(f"[STATE DONE] {state_name}: {sr.summary()}")
        return sr

    # ── City loop ──

    async def _process_city(self, city_res: CityResolution, state_name: str):
        city = city_res.city
        logger.log(f"\n  {'─'*50}\n  CITY: {city}, {state_name}\n  {'─'*50}")
        city_res.status = IN_PROGRESS

        for wave in range(1, MAX_WAVES + 1):
            if not self.running:
                break
            unresolved = [k for k, v in city_res.categories.items() if v.status not in (RESOLVED, FAILED)]
            if not unresolved:
                break
            logger.log(f"\n  [WAVE {wave}/{MAX_WAVES}] Unresolved: {', '.join(unresolved)}")
            for cat_key in unresolved:
                if not self.running:
                    break
                await self._process_category_wave(
                    city, state_name, cat_key, CATEGORY_LABELS[cat_key],
                    city_res.categories[cat_key], city_res, wave)
            if city_res.is_resolved():
                break

        for v in city_res.categories.values():
            if v.status not in (RESOLVED, FAILED):
                v.status = FAILED
                v.failure_reason = f"Exhausted {MAX_WAVES} waves"
        city_res.status = RESOLVED if city_res.is_resolved() else PARTIAL
        logger.log(f"  [CITY DONE] {city}: {city_res.summary()}")

    # ── Category wave — the main work ──

    async def _process_category_wave(self, city, state_name, cat_key, cat_label, cat_res, city_res, wave):
        cat_res.status = IN_PROGRESS
        cat_res.waves_attempted = wave
        log = logger.log

        # ─── PHASE 1: Generate queries ───
        queries = await self._generate_queries(city, state_name, cat_key, cat_label, wave, cat_res)
        if not queries:
            log(f"      [P1] No queries generated")
            cat_res.status = FAILED
            cat_res.failure_reason = "No queries"
            return

        # ─── CHECKPOINT 1: Validate queries ───
        cp1 = await checkpoint("queries_ready", {
            "state": state_name, "city": city, "category": cat_label, "wave": wave,
            "queries": [{"num": i + 1,
                         "query": qd.get("query", "") if isinstance(qd, dict) else str(qd),
                         "angle": qd.get("angle", "?") if isinstance(qd, dict) else "?"}
                        for i, qd in enumerate(queries)],
            "message": f"{len(queries)} requetes pour {city} / {cat_label} (vague {wave}). Valider?",
        })
        if cp1 == "skip":
            cat_res.status = FAILED
            cat_res.failure_reason = "Skipped by user"
            return
        if cp1 == "modify" and app_state.checkpoint_modifications.get("queries"):
            new_qs = app_state.checkpoint_modifications["queries"]
            queries = [{"query": q["query"], "angle": q.get("angle", "custom")}
                       for q in new_qs if q.get("query", "").strip()]
            log(f"      [P1] User modified → {len(queries)} queries")

        # ─── PHASE 2: Browser search ───
        all_results, query_entries = await self._search(
            queries, city, state_name, cat_key, cat_label, wave, cat_res)

        # Dedup
        seen = set()
        unique = [r for r in all_results
                  if r.get("url") not in seen and not seen.add(r.get("url", ""))]
        log(f"      [P2] {len(all_results)} total → {len(unique)} unique")

        if not unique:
            save_search_csv(state_name, city, cat_key, query_entries)
            self.cost.report_result("direct", found=0, cost=len(queries))
            await self._escalate(city, state_name, cat_key, cat_label, cat_res, wave, queries, 0, 0, 0, 0)
            return

        # CostEngine: report search results
        yt_in_results = sum(1 for r in unique if "youtube.com" in r.get("url", ""))
        source_tier = "direct" if wave == 1 else ("semi_direct" if wave == 2 else "indirect")
        self.cost.report_result(source_tier, found=yt_in_results, cost=len(queries),
                                query=f"{city}/{cat_label}/wave{wave}")

        # ─── CHECKPOINT 2: Review search results ───
        yt_found = [r for r in unique if "youtube.com" in r.get("url", "") or "youtube.com" in r.get("domain", "")]
        cp2 = await checkpoint("search_done", {
            "state": state_name, "city": city, "category": cat_label, "wave": wave,
            "total_links": len(unique), "youtube_links": len(yt_found),
            "top_results": [{"url": r.get("url", ""), "title": r.get("title", "")[:80]}
                            for r in unique[:30]],
            "message": f"{len(unique)} liens ({len(yt_found)} YouTube). Analyser?",
        })
        if cp2 == "skip":
            save_search_csv(state_name, city, cat_key, query_entries)
            cat_res.status = FAILED
            cat_res.failure_reason = "Skipped after search"
            return

        # ─── PHASE 3: Triage ───
        log(f"      [P3] Scoring {len(unique)} results...")
        scored = await triage_results(unique, city, state_name, cat_label, MIN_TRIAGE_SCORE, query_llm)
        to_fetch = scored[:MAX_PAGES_TO_FETCH]
        log(f"      [P3] {len(to_fetch)} pages to fetch")

        # Merge triage scores into query_entries
        score_map = {s.get("url", ""): {"score": s.get("score", ""), "reason": s.get("reason", "")} for s in scored}
        for qe in query_entries:
            for r in qe.get("results", []):
                if r["url"] in score_map:
                    r.update(score_map[r["url"]])
        save_search_csv(state_name, city, cat_key, query_entries)

        if not to_fetch:
            await self._escalate(city, state_name, cat_key, cat_label, cat_res, wave, queries, len(unique), 0, 0, 0)
            return

        # ─── PHASE 4: Fetch & extract ───
        log(f"      [P4] Fetching pages...")
        all_frags = []
        cross = []
        async with aiohttp.ClientSession() as session:
            for j, pi in enumerate(to_fetch):
                if not self.running:
                    break
                purl = pi.get("url", "")
                if not purl:
                    continue
                log(f"        Page {j + 1}/{len(to_fetch)}: {purl[:70]}")
                pd = await fetch_page(purl, session)
                if not pd["success"]:
                    log(f"          [SKIP] {pd.get('error', '')}")
                    continue
                frags, cr = await extract_fragments(pd, pi, city, state_name, cat_label, wave, query_llm)
                log(f"          {len(frags)} creators extracted")
                all_frags.extend(frags)
                cross.extend(cr)
        city_res.cross_city_fragments.extend(cross)
        log(f"      [P4] {len(all_frags)} fragments, {len(cross)} cross-city refs")

        if not all_frags:
            await self._escalate(city, state_name, cat_key, cat_label, cat_res, wave,
                                 queries, len(unique), len(to_fetch), 0, 0)
            return

        # ─── PHASE 5: Assembly ───
        log(f"      [P5] Assembling candidates...")
        candidates = await assemble_candidates(all_frags, city, state_name, cat_label, query_llm)
        log(f"      [P5] {len(candidates)} candidates")

        if not candidates:
            await self._escalate(city, state_name, cat_key, cat_label, cat_res, wave,
                                 queries, len(unique), len(to_fetch), len(all_frags), 0)
            return

        # ─── Feed into GraphScorer ───
        for cand in candidates:
            eid = self.graph.add_entity(
                name=cand.get("channel_name", "?"),
                kind="person",
                city=city,
                state=state_name,
                source_type="search_result",
                status="target_found",
            )
            if cand.get("channel_url"):
                self.graph.add_target(
                    url=cand["channel_url"],
                    entity_id=eid,
                    platform="youtube",
                    name=cand.get("channel_name", ""),
                    description=cand.get("description", ""),
                )

        # ─── CHECKPOINT 3: Review candidates ───
        cp3 = await checkpoint("candidates_found", {
            "state": state_name, "city": city, "category": cat_label, "wave": wave,
            "candidates": [{"name": c.get("channel_name", "?"), "url": c.get("channel_url", ""),
                            "evidence": c.get("city_evidence_strength", "?"),
                            "sources": len(c.get("city_evidence_sources", []))}
                           for c in candidates],
            "message": f"{len(candidates)} candidats. Verifier YouTube?",
        })
        if cp3 == "skip":
            cat_res.status = FAILED
            cat_res.failure_reason = "Skipped before verification"
            return

        # ─── PHASE 5b: Follow-ups (via browser, not HTTP) ───
        await self._followups(candidates, wave, log)

        # ─── PHASE 6+7: YouTube verification + scoring ───
        verified = await self._verify_youtube(
            candidates, city, state_name, cat_key, cat_label, log)

        if verified:
            best = max(verified, key=lambda c: c.total_score)
            cat_res.status = RESOLVED
            cat_res.best_candidate = best.to_dict()
            cat_res.candidates = [c.to_dict() for c in verified]
            log(f"      ✅ [RESOLVED] {cat_label}: {best.channel_name} (score: {best.total_score})")
            progress_callback({"type": "category_resolved", "state": state_name,
                               "city": city, "category": cat_key, "channel": best.to_dict()})
            save_verified_csv(state_name, city, cat_key, [c.to_dict() for c in verified])

            # Feed verified into graph scorer with scoring
            self.cost.report_result(source_tier, found=len(verified), cost=0, value=len(verified) * 20)
        else:
            log(f"      ❌ [NOT RESOLVED] {cat_label} — wave {wave}")
            if wave >= MAX_WAVES:
                cat_res.status = FAILED
                cat_res.failure_reason = f"No verified channel after {wave} waves"

    # ══════════════════════════════════════
    # SUB-METHODS (extracted from monolith)
    # ══════════════════════════════════════

    async def _generate_queries(self, city, state_name, cat_key, cat_label, wave, cat_res) -> List[Dict]:
        """Phase 1: get queries from StrategyPlanner or fallback to LLM."""
        log = logger.log

        # Try loading from saved plan first
        plan_queries = _load_plan_queries(city, state_name, cat_label, wave)
        if plan_queries:
            log(f"      [P1] Loaded {len(plan_queries)} queries from strategy plan (tier {wave})")
            return plan_queries[:12]

        # Fallback: use old query_generator with LLM
        log(f"      [P1] No plan found, generating queries via LLM (wave {wave})...")
        queries = await generate_queries(city, state_name, cat_key, cat_label,
                                          wave, cat_res.search_log, query_llm, log)
        log(f"      [P1] {len(queries)} queries generated")
        return queries

    async def _search(self, queries, city, state_name, cat_key, cat_label, wave, cat_res):
        """Phase 2: browser navigation, save HTML, parse results."""
        log = logger.log
        log(f"      [P2] Searching via browser...")
        all_results = []
        query_entries = []
        browser = None

        try:
            from web_search.web_search_core.browser import StealthBrowser
            browser = StealthBrowser()
            await browser.start()
            log(f"      [P2] Firefox started")
        except Exception as e:
            log(f"      [P2] Browser failed: {str(e)[:80]} — falling back to HTTP")
            browser = None

        if browser:
            try:
                for i, qd in enumerate(queries):
                    if not self.running:
                        break
                    q = qd.get("query", "") if isinstance(qd, dict) else str(qd)
                    if not q:
                        continue
                    angle = qd.get("angle", "?") if isinstance(qd, dict) else "?"
                    query_num = i + 1

                    # CostEngine check: is this query worth doing?
                    src = qd.get("source_type", "direct")
                    if src not in self.cost.sources:
                        self.cost.add_source(src, priority=50)
                    ev = self.cost.evaluate_action(src)
                    if not ev["execute"] and i > 2:
                        log(f"        [COST] Skipping R{query_num}: {ev['reason']}")
                        continue

                    log(f"        R{query_num}/{len(queries)}: {q[:70]}")

                    for engine in ["brave", "google"]:
                        if not self.running:
                            break
                        log(f"          [{engine.upper()}]")

                        for page_num in range(PAGES_PER_QUERY):
                            if not self.running:
                                break

                            if engine == "google":
                                ok = await browser.search_google(q, page_num)
                            else:
                                ok = await browser.search_brave(q, page_num)

                            if not ok:
                                log(f"            [SKIP] Navigation failed p{page_num + 1}")
                                break

                            # Build folder path
                            step_folder = f"Etape_{wave}_{_safe(cat_label)}"
                            safe_q = _safe(q[:40])
                            query_folder = f"Requete_{query_num}_{safe_q}"
                            results_dir = (BASE_DIR / "RESULTATS" /
                                           _safe(state_name) / _safe(city) /
                                           step_folder / query_folder)
                            results_dir.mkdir(parents=True, exist_ok=True)

                            filename = f"{engine}_p{page_num + 1}.html"
                            html_path = results_dir / filename
                            save_result = await browser.save_page_html(html_path)

                            if save_result["success"]:
                                log(f"            Saved: {step_folder}/{query_folder}/{filename}")
                                parsed = parse_search_html(str(html_path))
                                save_parsed_csv(str(html_path), parsed)

                                qe_results = []
                                for link in parsed.get("links", []):
                                    r = {"url": link.get("url", ""), "title": link.get("title", ""),
                                         "snippet": link.get("snippet", ""), "domain": link.get("domain", ""),
                                         "source_query": q, "angle": angle, "engine": engine,
                                         "page_num": page_num + 1,
                                         "html_file": str(html_path.relative_to(BASE_DIR))}
                                    all_results.append(r)
                                    qe_results.append(r)

                                for yt_url in parsed.get("youtube_urls", []):
                                    r = {"url": yt_url, "title": "[YouTube found in page]",
                                         "snippet": "", "domain": "youtube.com",
                                         "source_query": q, "angle": angle, "engine": engine,
                                         "page_num": page_num + 1,
                                         "html_file": str(html_path.relative_to(BASE_DIR))}
                                    all_results.append(r)
                                    qe_results.append(r)

                                log(f"            Parsed: {parsed['link_count']} links, {len(parsed.get('youtube_urls', []))} YT")

                                query_entries.append({
                                    "query": q, "angle": angle, "wave": wave,
                                    "query_num": query_num, "engine": engine,
                                    "html_file": str(html_path.relative_to(BASE_DIR)),
                                    "results": [{"url": r["url"], "title": r["title"],
                                                 "snippet": r.get("snippet", ""), "domain": r.get("domain", ""),
                                                 "page_num": page_num + 1, "score": "", "reason": ""}
                                                for r in qe_results]
                                })

                                # Push to UI log (capped)
                                app_state.query_log.append({
                                    "state": state_name, "city": city, "category": cat_key,
                                    "cat_label": cat_label, "wave": wave, "query": q, "angle": angle,
                                    "query_num": query_num, "engine": engine,
                                    "html_file": str(html_path.relative_to(BASE_DIR)),
                                    "results_count": len(qe_results),
                                    "results": [{"url": r["url"], "title": r["title"][:100],
                                                 "snippet": r.get("snippet", "")[:150]}
                                                for r in qe_results[:20]]
                                })
                                if len(app_state.query_log) > 200:
                                    app_state.query_log = app_state.query_log[-150:]

                                if parsed["link_count"] < 3:
                                    break
                            else:
                                log(f"            [FAIL] {save_result.get('error', '')[:60]}")
                                break

                            await asyncio.sleep(random.uniform(3, 7))
                        await asyncio.sleep(random.uniform(4, 9))

                    cat_res.search_log.append(qd if isinstance(qd, dict) else {"query": q})
                    await asyncio.sleep(random.uniform(5, 12))
            finally:
                await browser.close()
                log(f"      [P2] Browser closed")
        else:
            # HTTP fallback
            async with aiohttp.ClientSession() as session:
                from web_search.web_search import brave_search_paginated
                for i, qd in enumerate(queries):
                    q = qd.get("query", "") if isinstance(qd, dict) else str(qd)
                    if not q:
                        continue
                    angle = qd.get("angle", "?") if isinstance(qd, dict) else "?"
                    log(f"        Q{i + 1}/{len(queries)} [HTTP]: {q[:70]}")
                    res = await brave_search_paginated(q, session, max_pages=PAGES_PER_QUERY,
                                                       log_func=lambda m: log(f"        {m}"))
                    qe = {"query": q, "angle": angle, "wave": wave, "results": []}
                    for r in res:
                        r["source_query"] = q
                        r["angle"] = angle
                        qe["results"].append({"url": r.get("url", ""), "title": r.get("title", ""),
                                              "snippet": r.get("snippet", ""), "domain": r.get("domain", ""),
                                              "score": "", "reason": ""})
                    query_entries.append(qe)
                    all_results.extend(res)
                    cat_res.search_log.append(qd if isinstance(qd, dict) else {"query": q})

        return all_results, query_entries

    async def _followups(self, candidates, wave, log):
        """Phase 5b: follow-up searches for incomplete candidates."""
        incomplete = [c for c in candidates
                      if not c.get("channel_url") or c.get("city_evidence_strength") in ("weak", "none")]
        if not incomplete or wave >= MAX_WAVES:
            return

        log(f"      [P5b] Follow-ups for {len(incomplete)} incomplete candidates")
        # Use browser if possible, else HTTP
        try:
            from web_search.web_search_core.browser import StealthBrowser
            browser = StealthBrowser()
            await browser.start()
            try:
                for cand in incomplete[:5]:
                    name = cand.get("channel_name", "")
                    if not name:
                        continue
                    q = f'"{name}" youtube channel'
                    log(f"          Follow-up: {q[:60]}")
                    ok = await browser.search_brave(q, 0)
                    if ok:
                        html = await browser.get_page_content()
                        if html and "youtube.com" in html:
                            parsed = parse_search_html(html)
                            for yt_url in parsed.get("youtube_urls", []):
                                if not cand.get("channel_url"):
                                    cand["channel_url"] = yt_url
                                    log(f"          [FOUND] {yt_url}")
                                    break
                    await asyncio.sleep(random.uniform(3, 6))
            finally:
                await browser.close()
        except Exception:
            # Fallback to HTTP
            async with aiohttp.ClientSession() as session:
                await run_followups(incomplete, candidates, session, query_llm, log)

    async def _verify_youtube(self, candidates, city, state_name, cat_key, cat_label, log) -> List[ChannelCandidate]:
        """Phase 6+7: YouTube verification + adversarial + graph scoring."""
        verified = []
        async with aiohttp.ClientSession() as session:
            for cand in candidates:
                if not self.running:
                    break
                yurl = cand.get("channel_url", "")
                if not yurl or "youtube.com" not in yurl:
                    continue

                log(f"        Checking: {cand.get('channel_name', '?')} ({yurl[:50]})")
                yt = await verify_youtube_channel(yurl, session)
                if not yt.get("exists"):
                    log(f"          [REJECT] Not found")
                    continue
                if not yt.get("subscriber_in_range"):
                    log(f"          [REJECT] Subs: {yt.get('subscribers_count', 0)}")
                    continue

                # Adversarial city check
                adv = await verify_city(cand, yt, city, state_name, query_llm)
                city_score = adv.get("final_city_score", 0.5) if adv else 0.5
                log(f"          City score: {city_score}")
                if city_score < MIN_CITY_SCORE:
                    log(f"          [REJECT] City too weak")
                    continue

                # Category check
                cat_r = await verify_category(cand, yt, cat_label, query_llm)
                cat_score = cat_r.get("category_score", 0.5) if cat_r else 0.5
                if cat_r and not cat_r.get("matches_category", True) and cat_score < 0.3:
                    log(f"          [REJECT] Category mismatch")
                    continue

                # Build ChannelCandidate
                ch = ChannelCandidate(
                    channel_name=yt.get("channel_name", cand.get("channel_name", "")),
                    channel_url=yurl, target_city=city, target_state=state_name, target_category=cat_key,
                    city_evidence=[{"quote": q, "source_url": cand.get("city_evidence_sources", [""])[idx]
                                    if idx < len(cand.get("city_evidence_sources", [])) else ""}
                                   for idx, q in enumerate(cand.get("city_evidence_quotes", []))],
                    independent_sources=len(set(cand.get("city_evidence_sources", []))),
                    city_score=city_score, category_score=cat_score,
                    yt_verified=True, yt_exists=True, yt_real_name=yt.get("channel_name", ""),
                    yt_subscribers_text=yt.get("subscribers_text", ""),
                    yt_subscribers_count=yt.get("subscribers_count", 0),
                    yt_subscriber_match=yt.get("subscriber_in_range", False),
                    yt_last_upload_text=yt.get("last_upload_text", ""),
                    yt_last_upload_recent=yt.get("last_upload_recent", False),
                    yt_description=yt.get("description", ""),
                )
                ch.compute_total_score()
                ch.verified = ch.total_score >= MIN_TOTAL_SCORE and ch.yt_subscriber_match
                log(f"          SCORE: {ch.total_score} | Verified: {ch.verified}")

                if ch.verified:
                    verified.append(ch)

                    # ─── Feed into GraphScorer ───
                    eid = self.graph.add_entity(
                        name=ch.channel_name, kind="person", city=city, state=state_name,
                        source_type="youtube_verified", status="validated")
                    tid = self.graph.add_target(
                        url=yurl, entity_id=eid, platform="youtube",
                        name=ch.yt_real_name, description=ch.yt_description[:500],
                        followers=ch.yt_subscribers_count,
                        is_active=ch.yt_last_upload_recent,
                        location_detected=city_score >= 0.5,
                        topic_detected=cat_score >= 0.5,
                        is_creator=True,
                    )
                    # Score with configured criteria (if any)
                    criteria = self.graph.get_criteria()
                    if criteria:
                        for cr in criteria:
                            met = False
                            name_cr = cr["name"]
                            if "diplome" in name_cr:
                                met = bool(cand.get("education_evidence"))
                            elif "localisation" in name_cr or "location" in name_cr:
                                met = city_score >= 0.5
                            elif "mots_cles" in name_cr or "keyword" in name_cr:
                                met = cat_score >= 0.5
                            elif "site" in name_cr or "external" in name_cr:
                                met = bool(yt.get("external_links"))
                            elif "activite" in name_cr or "recent" in name_cr:
                                met = ch.yt_last_upload_recent
                            self.graph.set_criterion(tid, name_cr, met)
                        self.graph.compute_score(tid)

        return verified

    async def _escalate(self, city, state, cat_key, cat_label, cat_res, wave, queries, tr, pf, fr, vr):
        if wave >= MAX_WAVES:
            cat_res.status = FAILED
            cat_res.failure_reason = f"Exhausted {wave} waves (results:{tr},pages:{pf},frags:{fr})"
            return
        await analyze_failure(city, state, cat_label, wave, queries, tr, pf, fr, vr, query_llm, logger.log)

    def get_results(self) -> Dict:
        out = {}
        for sn, sr in self.states.items():
            out[sn] = {}
            for cn, cr in sr.cities.items():
                out[sn][cn] = {}
                for ck, cat in cr.categories.items():
                    out[sn][cn][ck] = (cat.best_candidate if cat.best_candidate
                                       else {"status": cat.status, "failure_reason": cat.failure_reason,
                                             "waves_attempted": cat.waves_attempted})
        return out


# ══════════════════════════════════════
# TOP-LEVEL SCAN
# ══════════════════════════════════════

async def run_full_scan():
    """Top-level scan function called by server."""
    app_state.scan_running = True
    app_state.progress["started_at"] = time.time()
    for k in ["completed_states", "completed_tasks", "resolved_tasks", "failed_tasks"]:
        app_state.progress[k] = 0
    app_state.results = {}
    app_state.resolution_status = {}

    pipe = PipelineOrchestrator()
    app_state.pipeline = pipe

    logger.log("=" * 60)
    logger.log("SCAN START — YouTube Scout v2")
    logger.log(f"Mode: {'AUTO' if app_state.auto_mode else 'VALIDATION'}")
    logger.log(f"Modules: StrategyPlanner={'plan found' if (BASE_DIR/'RESULTATS'/'strategy_plan.json').exists() else 'not found'}")
    logger.log(f"         GraphScorer=SQLite, CostEngine=active")
    logger.log(f"50 states x 3 cities x {len(CATEGORIES)} categories, max {MAX_WAVES} waves")
    logger.log("=" * 60)

    # Try to resume from last save
    resume_state = _load_resume()

    task_times = []
    for idx, (state_name, cities) in enumerate(US_STATES_CITIES.items()):
        if not app_state.scan_running:
            logger.log("SCAN CANCELLED")
            break
        # Skip already completed states (resume)
        if resume_state and state_name in resume_state:
            logger.log(f"[RESUME] Skipping {state_name} (already done)")
            app_state.progress["completed_states"] = idx + 1
            continue

        # CostEngine global check
        if pipe.cost.should_stop():
            logger.log(f"[COST] Global stop: {pipe.cost._stop_reason}")
            break

        app_state.progress["current_state"] = state_name
        t0 = time.time()
        sr = await pipe.process_state(state_name, cities)
        task_times.append(time.time() - t0)

        app_state.resolution_status[state_name] = sr.to_dict()
        for cr in sr.cities.values():
            for cat in cr.categories.values():
                app_state.progress["completed_tasks"] += 1
                if cat.status == RESOLVED:
                    app_state.progress["resolved_tasks"] += 1
                elif cat.status == FAILED:
                    app_state.progress["failed_tasks"] += 1
        app_state.progress["completed_states"] = idx + 1
        if task_times:
            remaining = len(US_STATES_CITIES) - (idx + 1)
            app_state.progress["eta_seconds"] = int(sum(task_times) / len(task_times) * remaining)
        app_state.results.update(pipe.get_results())

        # Save after every state (persistence for resume)
        _save()
        pipe.cost.save()

    app_state.scan_running = False
    _save()
    pipe.cost.save()

    r = app_state.progress
    logger.log("=" * 60)
    logger.log(f"SCAN COMPLETE: {r['resolved_tasks']} resolved / {r['failed_tasks']} failed / {r['completed_tasks']} total")

    # Graph stats
    stats = pipe.graph.get_stats()
    logger.log(f"GRAPH: {stats['entities']['total']} entities, {stats['targets']['total']} targets, "
               f"{stats['scores']['validated']} validated")
    logger.log(f"COST: {pipe.cost.total_actions} actions, efficiency {pipe.cost.summary().get('efficiency', 0):.3f}")
    logger.log("=" * 60)


def _save():
    """Save results + resolution status to disk."""
    p = BASE_DIR / "results.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "model": app_state.active_model,
            "results": app_state.results,
            "resolution": app_state.resolution_status
        }, f, indent=2, ensure_ascii=False)

    # Also save resolution for resume
    rp = BASE_DIR / "RESULTATS" / "_resume.json"
    rp.parent.mkdir(parents=True, exist_ok=True)
    with open(rp, "w", encoding="utf-8") as f:
        json.dump({"completed_states": list(app_state.resolution_status.keys()),
                    "progress": app_state.progress}, f, ensure_ascii=False)


def _load_resume() -> Optional[set]:
    """Load completed states for resume after crash."""
    rp = BASE_DIR / "RESULTATS" / "_resume.json"
    if not rp.exists():
        return None
    try:
        data = json.loads(rp.read_text(encoding="utf-8"))
        states = set(data.get("completed_states", []))
        if states:
            logger.log(f"[RESUME] Found {len(states)} completed states from previous run")
        return states
    except Exception:
        return None
