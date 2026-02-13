"""prompts/adversarial_prompt.py — Phase 6: Adversarial city verification."""
TEMPLATE = """You are a SKEPTICAL fact-checker. Your job is to CHALLENGE the claim that "{channel_name}" ({channel_url}) is based in {city}, {state}.

EVIDENCE SUPPORTING THE CLAIM:
{evidence_for}

YOUTUBE DATA:
  Channel name: {yt_real_name}
  Subscribers: {yt_subscribers}
  Description excerpt: {yt_description}

YOUR TASK — Try to DISPROVE the city claim:
1. Could this be a DIFFERENT person with the same name?
2. Could they have MOVED AWAY from {city}?
3. Could they have only VISITED {city} (not lived there)?
4. Is there any NAME CONFUSION (similar names, nicknames)?
5. Does the YouTube channel description CONTRADICT the city claim?
6. Are the evidence sources RELIABLE or could they be outdated?

SCORING:
  0.9-1.0: Strong evidence, multiple independent sources, hard to disprove
  0.7-0.8: Moderate evidence, 1-2 good sources, plausible
  0.5-0.6: Weak evidence, could go either way
  0.3-0.4: Very weak, probably wrong city
  0.0-0.2: Almost certainly wrong

JSON only: {{"skepticism_level":"low/medium/high","concerns":["specific concern 1","concern 2"],"evidence_quality":"strong/moderate/weak","likely_correct":true,"final_city_score":0.0,"reasoning":"brief explanation"}}"""
