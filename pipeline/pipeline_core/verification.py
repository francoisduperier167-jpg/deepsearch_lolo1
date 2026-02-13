"""pipeline/pipeline_core/verification.py — Phase 6: Adversarial verification.
INPUT: candidate dict + YouTube data | OUTPUT: city_score, category_score
"""
import json
from typing import Dict, Callable, Optional
from prompts.adversarial_prompt import TEMPLATE as ADV_TEMPLATE
from prompts.category_prompt import TEMPLATE as CAT_TEMPLATE

async def verify_city(candidate: Dict, yt_data: Dict, city: str, state: str,
    llm_func: Callable) -> Optional[Dict]:
    return await llm_func(ADV_TEMPLATE.format(
        channel_name=yt_data.get("channel_name",candidate.get("channel_name","")),
        channel_url=candidate.get("channel_url",""), city=city, state=state,
        evidence_for=json.dumps(candidate.get("city_evidence_quotes",[]),indent=2),
        yt_real_name=yt_data.get("channel_name",""), yt_subscribers=yt_data.get("subscribers_text",""),
        yt_description=yt_data.get("description","")[:200]))

async def verify_category(candidate: Dict, yt_data: Dict, cat_label: str,
    llm_func: Callable) -> Optional[Dict]:
    return await llm_func(CAT_TEMPLATE.format(
        channel_name=yt_data.get("channel_name",candidate.get("channel_name","")),
        channel_url=candidate.get("channel_url",""),
        yt_description=yt_data.get("description","")[:200], category_label=cat_label,
        category_evidence=json.dumps(candidate.get("category_evidence_quotes",[]))))
