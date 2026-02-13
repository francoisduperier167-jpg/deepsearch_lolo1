"""config/strategy.py — Load and parse the research strategy file.

The strategy file defines steps for the LLM to follow when searching.
Users can edit strategy.txt at any time — it's reloaded for each city.
"""
import re
from pathlib import Path
from typing import List, Dict
from config.settings import BASE_DIR


STRATEGY_FILE = BASE_DIR / "strategy.txt"

DEFAULT_STRATEGY = """[OBJECTIF]
Trouver des chaines YouTube actives de createurs bases a {city}, {state} 
dans la categorie {cat_label}, avec {sub_min} a {sub_max} abonnes.

[ETAPE 1 — Recherche directe]
Requetes a formuler:
- "{city}" youtuber {cat_label}
- site:reddit.com "{city}" youtube {cat_label}

[ETAPE 2 — Presse locale]  
Requetes a formuler:
- "{city}" local creator {cat_label} interview
- "{city}" "content creator" {cat_label} profile
"""


def load_strategy() -> str:
    """Load strategy from file, or return default."""
    if STRATEGY_FILE.exists():
        try:
            return STRATEGY_FILE.read_text(encoding='utf-8')
        except Exception:
            pass
    return DEFAULT_STRATEGY


def save_strategy(text: str):
    """Save strategy text to file."""
    STRATEGY_FILE.write_text(text, encoding='utf-8')


def parse_steps(strategy_text: str) -> List[Dict]:
    """Parse strategy text into structured steps.
    
    Returns: [{"number": 1, "name": "Recherche directe", "queries_template": [...], "raw": "..."}]
    """
    steps = []
    # Split by [ETAPE N — Name]
    pattern = r'\[ETAPE\s+(\d+)\s*[—-]\s*([^\]]+)\](.*?)(?=\[ETAPE|\[NOTES\]|$)'
    for m in re.finditer(pattern, strategy_text, re.DOTALL | re.IGNORECASE):
        num = int(m.group(1))
        name = m.group(2).strip()
        body = m.group(3).strip()
        
        # Extract query templates (lines starting with -)
        queries = []
        for line in body.split('\n'):
            line = line.strip()
            if line.startswith('- '):
                q = line[2:].strip().strip('"').strip("'")
                if q:
                    queries.append(q)
        
        steps.append({
            "number": num,
            "name": name,
            "queries_template": queries,
            "raw": body,
        })
    
    return steps


def get_objective(strategy_text: str) -> str:
    """Extract the [OBJECTIF] section."""
    m = re.search(r'\[OBJECTIF\]\s*(.*?)(?=\[ETAPE|\[NOTES\]|$)', strategy_text, re.DOTALL)
    return m.group(1).strip() if m else ""


def format_step_queries(step: Dict, city: str, state: str, 
                        category: str, cat_label: str,
                        sub_min: int = 20000, sub_max: int = 150000) -> List[str]:
    """Fill in variables in query templates for a specific city/category.
    
    Returns list of ready-to-use search queries.
    """
    queries = []
    for template in step.get("queries_template", []):
        try:
            q = template.format(
                city=city, state=state, 
                category=category, cat_label=cat_label,
                sub_min=sub_min, sub_max=sub_max,
            )
            queries.append(q)
        except (KeyError, IndexError):
            # If a variable is unknown, use the raw template
            queries.append(template)
    return queries
