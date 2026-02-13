"""utils/json_extract.py — Robust JSON extraction from LLM output."""
import json, re
from typing import Optional
def extract_json(text: str) -> Optional[dict]:
    if not text: return None
    text = text.strip()
    try: return json.loads(text)
    except json.JSONDecodeError: pass
    c = re.sub(r'^```json\s*','',text); c = re.sub(r'^```\s*','',c); c = re.sub(r'\s*```$','',c).strip()
    try: return json.loads(c)
    except json.JSONDecodeError: pass
    m = re.search(r'\{[\s\S]*\}', text)
    if m:
        try: return json.loads(m.group())
        except json.JSONDecodeError: pass
    return None
