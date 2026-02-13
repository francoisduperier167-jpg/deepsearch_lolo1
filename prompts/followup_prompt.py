"""prompts/followup_prompt.py — Generate follow-up searches for incomplete candidates."""
TEMPLATE = """Some candidates are INCOMPLETE — they need more evidence. Generate targeted follow-up searches.

INCOMPLETE CANDIDATES:
{candidates_text}

MISSING INFORMATION: {missing_info}

For each candidate, generate 2-3 SPECIFIC search queries to find:
- Their YouTube channel URL (if missing)
- Confirmation they live in the target city
- Their subscriber count
- Their real name or additional identifiers

Use operators: site:youtube.com, site:twitter.com, quotes for exact names.

JSON only: {{"followup_queries":[{{"for_candidate":"candidate name","query":"specific search query","purpose":"what we hope to find"}}]}}"""
