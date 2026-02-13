"""web_search/web_search.py — Public interface, re-exports all web functions."""
from web_search.web_search_core.brave_search import brave_search_paginated
from web_search.web_search_core.page_fetcher import fetch_page
from web_search.web_search_core.youtube_checker import verify_youtube_channel

__all__ = ["brave_search_paginated", "fetch_page", "verify_youtube_channel"]
