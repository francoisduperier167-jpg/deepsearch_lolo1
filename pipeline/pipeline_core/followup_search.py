"""pipeline/pipeline_core/followup_search.py — Phase 5b: Follow-up searches.
INPUT: incomplete candidates | OUTPUT: updates candidates in-place with found URLs.

Uses LLM to generate follow-up queries, then searches via HTTP as last resort.
Browser-based follow-ups are handled in pipeline.py._followups() directly.
"""
import json
from typing import List, Dict, Callable
import aiohttp
from prompts.followup_prompt import TEMPLATE
from utils.logger import logger


async def run_followups(incomplete: List[Dict], all_candidates: List[Dict],
    session: aiohttp.ClientSession, llm_func: Callable, log: Callable):
    """HTTP-based follow-up search (fallback when browser unavailable)."""
    ctxt = json.dumps(incomplete[:5], indent=2, default=str)
    result = await llm_func(TEMPLATE.format(
        candidates_text=ctxt,
        missing_info="YouTube URL, city confirmation, subscriber count"))
    if not result or "followup_queries" not in result:
        return

    for fq in result["followup_queries"][:10]:
        q = fq.get("query", "")
        cname = fq.get("for_candidate", "")
        if not q:
            continue
        log(f"          Follow-up '{cname}': {q[:60]}...")

        # Simple HTTP search (may be blocked)
        try:
            from web_search.web_search_core.brave_search import brave_search_paginated
            results = await brave_search_paginated(
                q, session, max_pages=1,
                log_func=lambda m: log(f"            {m}"))
        except Exception as e:
            log(f"            [HTTP FAILED] {str(e)[:60]}")
            continue

        for r in results[:10]:
            url = r.get("url", "")
            if "youtube.com" in url:
                for c in all_candidates:
                    if not c.get("channel_url") and cname.lower() in c.get("channel_name", "").lower():
                        c["channel_url"] = url
                        log(f"            [FOUND URL] {url}")
                        break
