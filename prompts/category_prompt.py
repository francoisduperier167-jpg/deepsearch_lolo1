"""prompts/category_prompt.py — Phase 6b: Category verification."""
TEMPLATE = """Verify: Does YouTube channel "{channel_name}" ({channel_url}) match the category "{category_label}"?

YouTube description: {yt_description}
Category evidence from research: {category_evidence}

Evaluate:
1. Does the channel's content clearly match {category_label}?
2. Is this their PRIMARY content type or a secondary/occasional topic?
3. Could this channel be miscategorized?

JSON only: {{"matches_category":true,"category_score":0.0,"reasoning":"explanation","alternative_category":"if mismatched, what category fits better"}}
Score: 0.8-1.0=clear match, 0.5-0.7=partial, 0.3-0.4=weak, 0.0-0.2=mismatch"""
