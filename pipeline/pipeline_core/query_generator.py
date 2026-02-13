"""pipeline/pipeline_core/query_generator.py — Phase 1: Search strategy generation.
INPUT: city, state, category, wave | OUTPUT: list of query dicts
"""
import json
from typing import List, Dict, Callable, Awaitable, Optional
from prompts.strategy_prompt import TEMPLATE
from config.cities import CATEGORY_SEARCH_TERMS

async def generate_queries(city: str, state: str, cat_key: str, cat_label: str,
    wave: int, prev_queries: list, llm_func: Callable, log: Callable) -> List[Dict]:
    prev_ctx = ""
    if wave > 1 and prev_queries:
        prev_ctx = f"PREVIOUS WAVE FAILED. Queries tried: {json.dumps([q.get('query','') for q in prev_queries[-8:]])}. Use COMPLETELY DIFFERENT queries with different angles."
    terms = ", ".join(CATEGORY_SEARCH_TERMS.get(cat_key, []))
    result = await llm_func(TEMPLATE.format(city=city, state=state, category_label=cat_label,
        wave_number=wave, previous_wave_context=prev_ctx, category_terms=terms))

    queries = []
    if result and "queries" in result:
        if result.get("strategy_reasoning"):
            log(f"      Strategy: {result['strategy_reasoning'][:120]}")
        queries = result["queries"]

    # Dedup: remove queries that are too similar
    queries = _dedup_queries(queries)

    # If LLM gave < 4 queries or bad quality, merge with fallbacks
    if len(queries) < 4:
        log(f"      [FALLBACK] LLM gave {len(queries)} queries, adding fallbacks")
        fallbacks = fallback_queries(city, state, cat_key, wave)
        seen = set(q.get("query","").lower().strip() for q in queries)
        for fb in fallbacks:
            if fb["query"].lower().strip() not in seen:
                queries.append(fb)
                seen.add(fb["query"].lower().strip())
    return queries[:8]

def _dedup_queries(queries: List[Dict]) -> List[Dict]:
    """Remove queries that differ only by 1-2 words."""
    if not queries: return queries
    unique = []
    seen_words = []
    for q in queries:
        text = q.get("query","").lower()
        words = set(text.split())
        is_dup = False
        for prev in seen_words:
            overlap = len(words & prev) / max(len(words | prev), 1)
            if overlap > 0.7:  # >70% same words = too similar
                is_dup = True; break
        if not is_dup:
            unique.append(q)
            seen_words.append(words)
    return unique

def fallback_queries(city, state, cat_key, wave) -> List[Dict]:
    t = CATEGORY_SEARCH_TERMS.get(cat_key, ["content creator"])
    t1 = t[0]; t2 = t[1] if len(t)>1 else t[0]; t3 = t[2] if len(t)>2 else t1
    if wave == 1:
        return [
            {"angle":"direct",   "query": f'"{city}" youtuber {t1}'},
            {"angle":"reddit",   "query": f'site:reddit.com "{city}" youtube {t2}'},
            {"angle":"list",     "query": f'"youtubers from {state}" {t1} OR {t2}'},
            {"angle":"press",    "query": f'"{city}" "content creator" {t3} interview'},
            {"angle":"social",   "query": f'"{city}" {t1} youtube channel subscribers'},
            {"angle":"community","query": f'"{city}" "{t2}" "my channel" OR "subscribe"'},
        ]
    elif wave == 2:
        return [
            {"angle":"wide",     "query": f'"{state}" youtube channel {t1} 2024 OR 2025'},
            {"angle":"bio",      "query": f'site:twitter.com OR site:instagram.com "{city}" {t1} youtube'},
            {"angle":"event",    "query": f'"{city}" {t2} meetup OR convention OR festival'},
            {"angle":"forum",    "query": f'"{city}" {t1} recommendation OR underrated youtube'},
            {"angle":"collab",   "query": f'"{state}" {t3} youtuber collab OR feature'},
            {"angle":"news",     "query": f'"{city}" local {t1} creator OR influencer'},
        ]
    else:
        return [
            {"angle":"metro",    "query": f'"greater {city}" OR "{city} area" youtuber {t1}'},
            {"angle":"podcast",  "query": f'"{city}" {t2} podcast OR interview youtuber'},
            {"angle":"emerging", "query": f'"{state}" underrated {t1} youtube small channel'},
            {"angle":"best_of",  "query": f'"best {t1} youtubers" "{state}" OR "{city}"'},
            {"angle":"linkedin", "query": f'site:linkedin.com "{city}" youtube {t1} creator'},
            {"angle":"tiktok",   "query": f'"{city}" {t2} tiktok youtube creator'},
        ]
