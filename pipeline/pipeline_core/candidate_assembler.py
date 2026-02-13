"""pipeline/pipeline_core/candidate_assembler.py — Phase 5: Assemble candidates from fragments.
INPUT: list of fragments | OUTPUT: list of candidate dicts
"""
import json
from typing import List, Dict, Callable
from models.data_models import Fragment
from prompts.assembly_prompt import TEMPLATE

async def assemble_candidates(fragments: List[Fragment], city: str, state: str,
    cat_label: str, llm_func: Callable) -> List[Dict]:
    ftxt = ""
    for i, f in enumerate(fragments):
        try: data = json.loads(f.value) if isinstance(f.value,str) else f.value
        except: data = {"raw":f.value}
        ftxt += f"\n--- Fragment {i+1} (from: {f.source_url}, type: {f.source_type}) ---\n{json.dumps(data,indent=2)}\nContext: {f.context}\n"
    result = await llm_func(TEMPLATE.format(city=city, state=state, category_label=cat_label, fragments_text=ftxt[:15000]))
    if result and "candidates" in result: return result["candidates"]
    return []
