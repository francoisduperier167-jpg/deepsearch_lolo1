"""prompts/assembly_prompt.py — Phase 5: Assemble candidates from fragments."""
TEMPLATE = """You are an OSINT analyst. Consolidate fragments about YouTube creators into unique candidates.

TARGET: {city}, {state} - {category_label} - 20k to 150k subscribers

FRAGMENTS FROM MULTIPLE SOURCES:
{fragments_text}

CONSOLIDATION RULES:
1. GROUP fragments that refer to the SAME person (same name, same channel, same URL).
2. MERGE evidence from different sources — more independent sources = stronger evidence.
3. Be SKEPTICAL: if only one source mentions a creator in {city}, mark city_evidence as "weak".
4. A candidate needs BOTH a plausible city connection AND a YouTube presence.
5. Rank candidates by evidence strength: strong > moderate > weak.

EVIDENCE STRENGTH:
  strong: 2+ independent sources confirm city + found YouTube URL
  moderate: 1 source confirms city + YouTube URL found
  weak: City mentioned vaguely OR no YouTube URL found
  none: No city evidence at all

For each candidate, list EXACTLY what sources say (no fabrication).

JSON only:
{{"candidates":[{{"channel_name":"","channel_url":"","alternative_names":[],"city_evidence_strength":"strong/moderate/weak/none","city_evidence_sources":["source URLs"],"city_evidence_quotes":["exact quotes"],"category_evidence_strength":"","category_evidence_quotes":[],"subscriber_info":"","missing_info":["what we still need"],"overall_confidence":"high/medium/low","reasoning":"why this candidate is likely valid"}}],"suggested_followup_queries":["specific search queries to fill gaps"]}}"""
