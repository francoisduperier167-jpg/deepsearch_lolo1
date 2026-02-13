"""pipeline/pipeline_core/page_extractor.py — Phase 4: Extract creator fragments from pages.
INPUT: page data, context | OUTPUT: list of Fragment dicts + cross-city refs
"""
import json
from typing import List, Dict, Tuple, Callable
from models.data_models import Fragment
from prompts.extraction_prompt import TEMPLATE

async def extract_fragments(page_data: Dict, page_info: Dict, city: str, state: str,
    cat_label: str, wave: int, llm_func: Callable) -> Tuple[List[Fragment], List[Dict]]:
    yt_links = "\n".join(page_data.get("youtube_urls",[])) or "None"
    result = await llm_func(TEMPLATE.format(
        city=city, state=state, category_label=cat_label,
        source_url=page_data.get("url",""), page_title=page_data.get("title",""),
        page_text=page_data["text"][:12000], youtube_links=yt_links))
    fragments = []; cross = []
    if result and result.get("page_relevant"):
        for cr in result.get("creators_mentioned",[]):
            fragments.append(Fragment(fragment_type="creator_profile", value=json.dumps(cr),
                source_url=page_data.get("url",""), source_type=page_info.get("angle","unknown"),
                context=cr.get("city_quote",""), search_query=page_info.get("source_query",""), search_wave=wave))
        cross = result.get("other_cities_mentioned",[])
    return fragments, cross
