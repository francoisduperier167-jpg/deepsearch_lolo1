"""pipeline/pipeline_core/result_triage.py — Phase 3: Score search results.
INPUT: list of search results, city/state/cat | OUTPUT: sorted list with scores
"""
from typing import List, Dict, Callable, Awaitable
from prompts.triage_prompt import TEMPLATE

async def triage_results(results: List[Dict], city: str, state: str, cat_label: str,
    min_score: int, llm_func: Callable) -> List[Dict]:
    batch_size = 30; all_scored = []
    for i in range(0, len(results), batch_size):
        batch = results[i:i+batch_size]
        rtxt = ""
        for j, r in enumerate(batch):
            rtxt += f"\n[{j+1}] URL: {r.get('url','')}\n    Title: {r.get('title','')}\n    Snippet: {r.get('snippet','')[:200]}\n    Domain: {r.get('domain','')}\n"
        scored = await llm_func(TEMPLATE.format(city=city, state=state, category_label=cat_label,
            result_count=len(batch), results_text=rtxt))
        if scored and "scored_results" in scored:
            for s in scored["scored_results"]:
                url = s.get("url","")
                for r in batch:
                    if r.get("url")==url: s.update(r); break
                all_scored.append(s)
    all_scored.sort(key=lambda x: x.get("score",0), reverse=True)
    return [s for s in all_scored if s.get("score",0) >= min_score]
