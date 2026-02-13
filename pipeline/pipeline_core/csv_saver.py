"""pipeline/pipeline_core/csv_saver.py — Save search results as CSV files.
Structure: RESULTATS/{state}/{city}/recherche_{category}.csv
"""
import csv, os, re
from pathlib import Path
from typing import List, Dict
from config.settings import BASE_DIR


def safe_name(s: str) -> str:
    """Sanitize string for use as folder/file name."""
    return re.sub(r'[^\w\s-]', '', s).strip().replace(' ', '_')


def save_search_csv(state: str, city: str, category: str, query_entries: List[Dict]):
    """Save all search results for one state/city/category to CSV.
    
    query_entries: list of {query, angle, wave, results: [{url, title, snippet, domain, score, triage_reason}]}
    """
    base = BASE_DIR / "RESULTATS" / safe_name(state) / safe_name(city)
    base.mkdir(parents=True, exist_ok=True)
    
    fpath = base / f"recherche_{safe_name(category)}.csv"
    
    rows = []
    for qe in query_entries:
        query = qe.get("query", "")
        angle = qe.get("angle", "")
        wave = qe.get("wave", 1)
        for r in qe.get("results", []):
            rows.append({
                "wave": wave,
                "angle": angle,
                "query": query,
                "url": r.get("url", ""),
                "title": r.get("title", ""),
                "snippet": r.get("snippet", "")[:300],
                "domain": r.get("domain", ""),
                "triage_score": r.get("score", ""),
                "triage_reason": r.get("reason", ""),
                "page_num": r.get("page_num", ""),
            })
    
    if not rows:
        return
    
    fieldnames = ["wave", "angle", "query", "url", "title", "snippet", "domain",
                  "triage_score", "triage_reason", "page_num"]
    
    with open(fpath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def save_verified_csv(state: str, city: str, category: str, candidates: List[Dict]):
    """Save verified candidates for one category."""
    base = BASE_DIR / "RESULTATS" / safe_name(state) / safe_name(city)
    base.mkdir(parents=True, exist_ok=True)
    
    fpath = base / f"resultats_{safe_name(category)}.csv"
    
    rows = []
    for c in candidates:
        rows.append({
            "channel_name": c.get("channel_name") or c.get("yt_real_name", ""),
            "channel_url": c.get("channel_url", ""),
            "subscribers": c.get("yt_subscribers_count") or c.get("yt_subscribers_text", ""),
            "city_score": c.get("city_score", ""),
            "category_score": c.get("category_score", ""),
            "total_score": c.get("total_score", ""),
            "verified": c.get("verified", ""),
            "last_upload": c.get("yt_last_upload_text", ""),
            "description": (c.get("yt_description") or c.get("description", ""))[:200],
        })
    
    if not rows:
        return
    
    fieldnames = ["channel_name", "channel_url", "subscribers", "city_score",
                  "category_score", "total_score", "verified", "last_upload", "description"]
    
    with open(fpath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
