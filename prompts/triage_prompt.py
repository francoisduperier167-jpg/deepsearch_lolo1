"""prompts/triage_prompt.py — Phase 3: Score search results for relevance."""
TEMPLATE = """You are an OSINT search result evaluator. Score each search result for relevance.

TARGET: YouTube creators from {city}, {state}
CATEGORY: {category_label}
SUBSCRIBER RANGE: 20k - 150k

RESULTS TO EVALUATE ({result_count} results):
{results_text}

SCORING RULES (0-10):
  9-10: Directly lists YouTube creators from this city (listicle, directory, ranking)
  7-8:  Reddit thread, forum post, or article mentioning local YouTubers by name
  5-6:  Page that likely mentions video creators (blog, interview, local media)
  3-4:  Tangentially related (city mentioned, video topic mentioned, but unlikely to have YouTuber names)
  0-2:  Irrelevant (wrong city, wrong topic, corporate page, no creator info)

BOOST SIGNALS (add +1 or +2):
  - site:reddit.com → +2 (Reddit threads are gold for finding local creators)
  - "youtuber" or "content creator" in title → +2
  - "best of" or "top" lists → +2
  - Local newspaper / blog → +1
  - Contains "subscribe" or "channel" → +1

REJECT SIGNALS (set score to 0):
  - Generic YouTube homepage or trending page
  - Product/company pages unrelated to individual creators
  - Pages from a completely different city or country

Return ONLY results with score >= 4, sorted descending.
JSON only: {{"scored_results":[{{"url":"URL","score":8,"reason":"brief reason"}}]}}"""
