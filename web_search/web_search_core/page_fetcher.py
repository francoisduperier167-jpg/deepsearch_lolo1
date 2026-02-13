"""web_search/web_search_core/page_fetcher.py — Fetch page, extract text + YouTube URLs.
INPUT: URL | OUTPUT: {success, text, youtube_urls, title, error}
"""
import asyncio, re, random
from typing import Dict
from urllib.parse import urlparse
import aiohttp
from utils.rate_limiter import rate_limiter
from web_search.web_search_core.brave_search import USER_AGENTS

async def fetch_page(url: str, session: aiohttp.ClientSession, max_chars: int = 20000) -> Dict:
    result = {"url":url,"success":False,"text":"","youtube_urls":[],"title":"","error":None}
    await rate_limiter.wait(domain=urlparse(url).netloc)
    headers = {"User-Agent":random.choice(USER_AGENTS),"Accept":"text/html","Accept-Language":"en-US,en;q=0.9"}
    try:
        async with session.get(url,headers=headers,timeout=aiohttp.ClientTimeout(total=20),allow_redirects=True) as resp:
            if resp.status!=200: result["error"]=f"HTTP {resp.status}"; return result
            ct = resp.headers.get("Content-Type","")
            if "text/html" not in ct and "text/plain" not in ct: result["error"]=f"Not HTML: {ct[:50]}"; return result
            html = await resp.text(errors='replace')
            result["success"]=True
            tm = re.search(r'<title[^>]*>([^<]+)</title>',html,re.IGNORECASE)
            if tm: result["title"]=tm.group(1).strip()[:200]
            yt_pats = [r'https?://(?:www\.)?youtube\.com/@[\w\-\.]+',r'https?://(?:www\.)?youtube\.com/channel/UC[\w\-]+',
                       r'https?://(?:www\.)?youtube\.com/c/[\w\-]+',r'https?://(?:www\.)?youtube\.com/user/[\w\-]+']
            yturls = set()
            for p in yt_pats:
                for m in re.finditer(p,html): yturls.add(m.group(0))
            result["youtube_urls"]=list(yturls)
            for tag in ['script','style','nav','header','footer','aside','noscript','svg','iframe']:
                html = re.sub(f'<{tag}[^>]*>.*?</{tag}>','',html,flags=re.DOTALL|re.IGNORECASE)
            result["text"]=re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',html)).strip()[:max_chars]
    except asyncio.TimeoutError: result["error"]="Timeout"
    except Exception as e: result["error"]=str(e)[:100]
    return result
