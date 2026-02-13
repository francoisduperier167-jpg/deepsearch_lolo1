"""prompts/escalation_prompt.py — Analyze wave failure and suggest new strategy."""
TEMPLATE = """A search wave FAILED to find verified YouTube creators. Analyze why and suggest improvements.

CONTEXT:
  City: {city}, {state} | Category: {category_label} | Wave: {wave_number}/3
  Queries tried: {queries_used}
  Results: {total_results} search results → {pages_fetched} pages fetched → {candidates_found} candidates → {verified_count} verified

ANALYZE:
1. Were the queries too narrow? Too broad? Wrong angle?
2. Is this city too small for this category? Should we widen to metro area?
3. What search angles were NOT tried? (Reddit, local press, university alumni, events, social media bios)
4. Should we try completely different keywords or pivot to intermediaries?

JSON only: {{"failure_analysis":"what went wrong","city_viability":"high/medium/low","recommended_strategy":"what to try next","should_widen_geography":false,"wider_area_name":"metro area if applicable","new_angles":["angle1","angle2"]}}"""
