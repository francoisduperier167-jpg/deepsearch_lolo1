"""prompts/extraction_prompt.py — Phase 4: Extract creator fragments from fetched page."""
TEMPLATE = """You are an OSINT data extractor. Extract YouTube creator information from this web page.

CONTEXT:
  Target city: {city}, {state}
  Category: {category_label}
  Subscriber range: 20k - 150k

SOURCE PAGE:
  URL: {source_url}
  Title: {page_title}
  YouTube links found on page: {youtube_links}

PAGE CONTENT (truncated):
{page_text}

EXTRACTION RULES:
1. For EACH creator mentioned, extract:
   - name: Full name or channel name
   - youtube_url: Full URL if visible (e.g. youtube.com/@handle)
   - youtube_handle: Handle if visible (e.g. @handle)
   - city_quote: EXACT quote from the page that links this person to {city} (copy-paste, do NOT paraphrase)
   - category_quote: EXACT quote linking them to {category_label} content
   - subscriber_info: Any mention of subscriber/follower count
   - other_info: Any other useful info (real name, age, joined date, etc.)
   - confidence_city: How sure are you they're from {city}? high/medium/low/none
   - confidence_category: How sure they match {category_label}? high/medium/low/none

2. ONLY extract what is EXPLICITLY stated on the page. Do NOT guess or infer.
3. If the page mentions creators from OTHER cities, list them in other_cities_mentioned.
4. If the page is completely irrelevant, set page_relevant=false and return empty lists.

JSON only:
{{"page_relevant":true,"creators_mentioned":[{{"name":"","youtube_url":"","youtube_handle":"","city_quote":"EXACT QUOTE","category_quote":"EXACT QUOTE","subscriber_info":"","other_info":"","confidence_city":"high","confidence_category":"high"}}],"other_cities_mentioned":[{{"city":"","state":"","creator_name":""}}]}}"""
