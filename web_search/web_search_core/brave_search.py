"""web_search/web_search_core/brave_search.py — Brave Search with pagination.
INPUT: query string, max_pages | OUTPUT: list of {url, title, snippet, domain}
"""
import asyncio, random, re
from typing import List, Dict, Callable, Optional
from urllib.parse import quote_plus, urlparse
import aiohttp
from utils.rate_limiter import rate_limiter

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/605.1.15 Safari/605.1.15",
]
SKIP_DOMAINS = {'search.brave.com','brave.com','googleapis.com','gstatic.com','google.com','bing.com','microsoft.com'}

async def brave_search_paginated(query: str, session: aiohttp.ClientSession,
    max_pages: int = 2, log_func: Optional[Callable] = None) -> List[Dict]:
    all_results = []; seen = set(); consecutive_429 = 0
    for page in range(max_pages):
        if consecutive_429 >= 2:
            if log_func: log_func(f"    [STOP] Too many rate limits, skipping remaining pages")
            break
        offset = page * 20
        url = f"https://search.brave.com/search?q={quote_plus(query)}&offset={offset}"
        await rate_limiter.wait(domain="search.brave.com")
        headers = {"User-Agent": random.choice(USER_AGENTS), "Accept": "text/html",
                    "Accept-Language": "en-US,en;q=0.9", "DNT": "1",
                    "Referer": "https://search.brave.com/", "Sec-Fetch-Dest": "document"}
        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=20), allow_redirects=True) as resp:
                if resp.status == 429:
                    consecutive_429 += 1
                    wait = 30 * consecutive_429 + random.uniform(5, 15)
                    if log_func: log_func(f"    [RATE LIMITED] page {page+1}, waiting {int(wait)}s")
                    await asyncio.sleep(wait)
                    continue
                if resp.status != 200:
                    if log_func: log_func(f"    [HTTP {resp.status}] page {page+1}")
                    break
                consecutive_429 = 0
                html = await resp.text()
                page_results = _parse(html)
                if not page_results: break
                new = 0
                for r in page_results:
                    if r["url"] not in seen: seen.add(r["url"]); r["page_num"]=page+1; r["query"]=query; all_results.append(r); new+=1
                if log_func: log_func(f"    Page {page+1}: {new} new (total: {len(all_results)})")
                if new < 3: break
        except asyncio.TimeoutError:
            if log_func: log_func(f"    [TIMEOUT] page {page+1}")
            break
        except Exception as e:
            if log_func: log_func(f"    [ERROR] page {page+1}: {str(e)[:60]}")
            break
    return all_results

def _parse(html: str) -> List[Dict]:
    results = []; seen = set()
    def clean(t): return re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',re.sub(r'&amp;','&',re.sub(r'&lt;','<',re.sub(r'&gt;','>',re.sub(r'&quot;','"',re.sub(r'&#39;',"'",t))))))).strip()
    for m in re.finditer(r'<a[^>]*href="(https?://(?!search\.brave\.com|brave\.com)[^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL):
        url, text = m.group(1), clean(m.group(2))
        dom = urlparse(url).netloc.lower()
        if dom in SKIP_DOMAINS or url in seen or len(text)<5 or '/search?' in url or 'javascript:' in url: continue
        seen.add(url)
        snippet = ""
        surr = html[m.end():m.end()+1000]
        sm = re.search(r'(?:class="[^"]*(?:description|snippet|body|text)[^"]*"[^>]*>|<p[^>]*>)(.*?)(?:</|<br)', surr, re.DOTALL)
        if sm: snippet = clean(sm.group(1))
        elif len(surr) > 20: snippet = clean(surr[:300])
        results.append({"url":url,"title":text[:200],"snippet":snippet[:500],"domain":dom})
    return results
