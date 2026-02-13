"""prompts/strategy_prompt.py — Phase 1: Search strategy generation."""
TEMPLATE = """You are a web research strategist. Design a search strategy to find YouTube creators in a specific city.
TARGET: {city}, {state}, USA | Category: {category_label} | Subs: 20k-150k
WAVE: {wave_number}/3
{previous_wave_context}
Generate 6-8 queries using DIFFERENT ANGLES:
1. LOCAL_PRESS: "{city}" youtuber OR "content creator" + category
2. REDDIT: site:reddit.com "{city}" youtube + category
3. BEST_OF_LIST: "youtubers from {state}" + category
4. EVENTS: "{city}" youtube meetup OR convention + category
5. SOCIAL_BIO: site:twitter.com OR site:instagram.com "{city}" youtube + category
6. INTERVIEW: "{city}" youtuber interview OR podcast + category
7. REGIONAL: "{state}" content creator + category
8. COMMUNITY: "{city}" "subscribe" OR "my channel" + category
Category terms: {category_terms}
Respond ONLY with valid JSON:
{{"strategy_reasoning":"brief","queries":[{{"angle":"name","query":"the query","expected_yield":"what"}}]}}"""
