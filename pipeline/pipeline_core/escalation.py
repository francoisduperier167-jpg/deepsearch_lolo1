"""pipeline/pipeline_core/escalation.py — Analyze why a wave failed.
INPUT: wave stats | OUTPUT: analysis dict with recommendations
"""
import json
from typing import Dict, Callable, Optional
from prompts.escalation_prompt import TEMPLATE

async def analyze_failure(city: str, state: str, cat_label: str, wave: int,
    queries: list, total_results: int, pages_fetched: int, fragments: int,
    verified: int, llm_func: Callable, log: Callable) -> Optional[Dict]:
    qtxt = json.dumps([q.get("query",q) if isinstance(q,dict) else q for q in queries], indent=2)
    result = await llm_func(TEMPLATE.format(city=city,state=state,category_label=cat_label,
        wave_number=wave,queries_used=qtxt,total_results=total_results,pages_fetched=pages_fetched,
        candidates_found=fragments,verified_count=verified))
    if result:
        log(f"      [ESCALATION] {result.get('failure_analysis','?')[:120]}")
        log(f"      [ESCALATION] Viability: {result.get('city_viability','?')}")
    return result
