"""web_search/web_search_core/youtube_checker.py — Visit YouTube channel, extract real data.
INPUT: channel URL | OUTPUT: {exists, channel_name, subscribers_count, subscriber_in_range, last_upload_recent, ...}
"""
import asyncio, re, random
from typing import Dict
import aiohttp
from utils.rate_limiter import rate_limiter
from web_search.web_search_core.brave_search import USER_AGENTS
from config.settings import SUB_MIN, SUB_MAX

async def verify_youtube_channel(url: str, session: aiohttp.ClientSession) -> Dict:
    result = {"url":url,"exists":False,"channel_name":"","subscribers_text":"","subscribers_count":0,
              "subscriber_in_range":False,"last_upload_text":"","last_upload_recent":False,"description":"","error":None}
    if not url or 'youtube.com' not in url: result["error"]="Not YouTube"; return result
    clean_url = url.split('?')[0].rstrip('/')
    await rate_limiter.wait(domain="www.youtube.com")
    hdr = {"User-Agent":random.choice(USER_AGENTS),"Accept":"text/html","Accept-Language":"en-US,en;q=0.9"}
    try:
        async with session.get(clean_url,headers=hdr,timeout=aiohttp.ClientTimeout(total=25),allow_redirects=True) as resp:
            if resp.status==404: result["error"]="404"; return result
            if resp.status!=200: result["error"]=f"HTTP {resp.status}"; return result
            html = await resp.text(errors='replace')
            if any(m in html for m in ['"channelMetadataRenderer"','property="og:title"','"channelId"']): result["exists"]=True
            for p in [r'<meta property="og:title" content="([^"]+)"',r'"title":\s*"([^"]{2,80})"']:
                m=re.search(p,html,re.DOTALL)
                if m: result["channel_name"]=m.group(1).strip(); break
            for p in [r'"subscriberCountText":\s*\{[^}]*"simpleText":\s*"([^"]+)"',r'"subscriberCountText":\s*"([^"]+)"']:
                m=re.search(p,html)
                if m: result["subscribers_text"]=m.group(1).strip(); result["subscribers_count"]=_parse_subs(result["subscribers_text"]); result["subscriber_in_range"]=SUB_MIN<=result["subscribers_count"]<=SUB_MAX; break
            for p in [r'<meta property="og:description" content="([^"]*)"']:
                m=re.search(p,html)
                if m: result["description"]=m.group(1)[:300]; break
        await rate_limiter.wait(domain="www.youtube.com")
        async with session.get(clean_url+"/videos",headers=hdr,timeout=aiohttp.ClientTimeout(total=25),allow_redirects=True) as resp:
            if resp.status==200:
                html=await resp.text(errors='replace')
                for p in [r'"publishedTimeText":\s*\{[^}]*"simpleText":\s*"([^"]+)"',r'"publishedTimeText":\s*"([^"]+)"']:
                    m=re.search(p,html)
                    if m: result["last_upload_text"]=m.group(1).strip(); result["last_upload_recent"]=_is_recent(result["last_upload_text"]); break
    except asyncio.TimeoutError: result["error"]="Timeout"
    except Exception as e: result["error"]=str(e)[:100]
    return result

def _parse_subs(t):
    if not t: return 0
    t=t.strip().lower(); t=re.sub(r'\s*(subscribers|abonnés|abonnes)\s*','',t).strip().replace(',','').replace(' ','')
    try:
        if t.endswith('k'): return int(float(t[:-1])*1000)
        elif t.endswith('m'): return int(float(t[:-1])*1_000_000)
        else: return int(float(t))
    except: return 0

def _is_recent(t):
    if not t: return False
    t=t.lower()
    if any(w in t for w in ['hour','minute','second','heure']): return True
    if 'day' in t or 'jour' in t: m=re.search(r'(\d+)',t); return int(m.group(1))<=30 if m else True
    if 'week' in t or 'semaine' in t: m=re.search(r'(\d+)',t); return int(m.group(1))<=4 if m else True
    if 'month' in t or 'mois' in t: m=re.search(r'(\d+)',t); return int(m.group(1))<=1 if m else False
    return False
