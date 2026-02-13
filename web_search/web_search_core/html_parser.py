"""web_search/web_search_core/html_parser.py — Parse saved HTML search result pages.

Extracts from SingleFile-saved HTML:
- All links with titles and descriptions/snippets
- YouTube URLs found anywhere in the page
- Generates CSV output per page

Works with both Google and Brave Search HTML.
"""
import csv
import re
from pathlib import Path
from typing import List, Dict, Tuple
from html.parser import HTMLParser


class LinkExtractor(HTMLParser):
    """Extract all meaningful links from an HTML page."""
    
    def __init__(self):
        super().__init__()
        self.links: List[Dict] = []
        self.youtube_urls: set = set()
        self.current_link = None
        self.current_text = ""
        self.in_link = False
        self.in_script = False
        self.in_style = False
        self.all_text_chunks: List[str] = []
        
        # Domains to skip (search engine internal links)
        self.skip_domains = {
            'google.com', 'googleapis.com', 'gstatic.com', 'bing.com',
            'microsoft.com', 'brave.com', 'search.brave.com',
            'accounts.google.com', 'support.google.com', 'maps.google.com',
        }
    
    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        
        if tag == 'script':
            self.in_script = True
        elif tag == 'style':
            self.in_style = True
        elif tag == 'a':
            href = attrs_dict.get('href', '')
            if href and href.startswith('http') and not any(d in href for d in self.skip_domains):
                self.in_link = True
                self.current_link = href
                self.current_text = ""
                # Check for YouTube
                self._check_youtube(href)
        
        # Also check data-href, onclick for links
        for attr_name in ['data-href', 'data-url', 'cite']:
            val = attrs_dict.get(attr_name, '')
            if val and val.startswith('http'):
                self._check_youtube(val)
    
    def handle_endtag(self, tag):
        if tag == 'script':
            self.in_script = False
        elif tag == 'style':
            self.in_style = False
        elif tag == 'a' and self.in_link:
            self.in_link = False
            text = self.current_text.strip()
            if text and len(text) > 2 and self.current_link:
                self.links.append({
                    "url": self.current_link,
                    "title": text[:300],
                })
            self.current_link = None
    
    def handle_data(self, data):
        if self.in_script or self.in_style:
            return
        clean = data.strip()
        if clean:
            self.all_text_chunks.append(clean)
        if self.in_link:
            self.current_text += data
    
    def _check_youtube(self, url: str):
        """Extract YouTube channel/video URLs."""
        yt_patterns = [
            r'(https?://(?:www\.)?youtube\.com/@[\w.-]+)',
            r'(https?://(?:www\.)?youtube\.com/channel/UC[\w-]+)',
            r'(https?://(?:www\.)?youtube\.com/c/[\w.-]+)',
            r'(https?://(?:www\.)?youtube\.com/user/[\w.-]+)',
            r'(https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+)',
        ]
        for pat in yt_patterns:
            m = re.search(pat, url)
            if m:
                self.youtube_urls.add(m.group(1))


def parse_search_html(html_path: str) -> Dict:
    """Parse a saved search results HTML file.
    
    Returns: {
        "links": [{"url", "title", "snippet", "domain"}],
        "youtube_urls": ["url1", ...],
        "full_text": "all text on the page",
        "link_count": int,
    }
    """
    path = Path(html_path)
    if not path.exists():
        return {"links": [], "youtube_urls": [], "full_text": "", "link_count": 0, "error": "File not found"}
    
    try:
        html = path.read_text(encoding='utf-8', errors='replace')
    except Exception as e:
        return {"links": [], "youtube_urls": [], "full_text": "", "link_count": 0, "error": str(e)}
    
    # Parse with our extractor
    extractor = LinkExtractor()
    try:
        extractor.feed(html)
    except Exception:
        pass
    
    # Also find YouTube URLs in raw HTML (they might be in JS or data attributes)
    for m in re.finditer(r'https?://(?:www\.)?youtube\.com/(?:@|channel/|c/|user/)[\w.-]+', html):
        extractor.youtube_urls.add(m.group(0))
    
    # Try to extract snippets by looking at text near links
    links_with_snippets = _enrich_with_snippets(extractor.links, html)
    
    # Add domain
    for link in links_with_snippets:
        m = re.match(r'https?://([^/]+)', link.get("url", ""))
        link["domain"] = m.group(1) if m else ""
    
    # Deduplicate
    seen = set()
    unique_links = []
    for link in links_with_snippets:
        url = link.get("url", "")
        if url not in seen:
            seen.add(url)
            unique_links.append(link)
    
    full_text = " ".join(extractor.all_text_chunks)
    
    return {
        "links": unique_links,
        "youtube_urls": sorted(extractor.youtube_urls),
        "full_text": full_text[:50000],  # Cap for LLM
        "link_count": len(unique_links),
    }


def _enrich_with_snippets(links: List[Dict], html: str) -> List[Dict]:
    """Try to find description/snippet text near each link in the HTML."""
    for link in links:
        url = re.escape(link.get("url", ""))
        if not url:
            continue
        # Look for text after the link
        pattern = re.compile(url + r'.*?</a>\s*(.*?)(?:<a |<div |<li |<h[1-6]|$)', re.DOTALL | re.IGNORECASE)
        m = pattern.search(html)
        if m:
            snippet_raw = m.group(1)
            # Strip HTML tags
            snippet = re.sub(r'<[^>]+>', ' ', snippet_raw)
            snippet = re.sub(r'\s+', ' ', snippet).strip()
            if 10 < len(snippet) < 500:
                link["snippet"] = snippet[:300]
            else:
                link["snippet"] = ""
        else:
            link["snippet"] = ""
    return links


def save_parsed_csv(html_path: str, parsed: Dict, output_csv: str = ""):
    """Save parsed results to a CSV file next to the HTML file.
    
    CSV columns: url, title, snippet, domain, is_youtube
    """
    if not output_csv:
        output_csv = str(Path(html_path).with_suffix('.csv'))
    
    rows = []
    for link in parsed.get("links", []):
        is_yt = "youtube.com" in link.get("url", "")
        rows.append({
            "url": link.get("url", ""),
            "title": link.get("title", ""),
            "snippet": link.get("snippet", ""),
            "domain": link.get("domain", ""),
            "is_youtube": "yes" if is_yt else "",
        })
    
    # Also add standalone YouTube URLs found in page but not in links
    link_urls = set(l.get("url", "") for l in parsed.get("links", []))
    for yt_url in parsed.get("youtube_urls", []):
        if yt_url not in link_urls:
            rows.append({
                "url": yt_url,
                "title": "[YouTube channel found in page]",
                "snippet": "",
                "domain": "youtube.com",
                "is_youtube": "yes",
            })
    
    if not rows:
        return
    
    fieldnames = ["url", "title", "snippet", "domain", "is_youtube"]
    with open(output_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_and_save(html_path: str) -> Dict:
    """Parse an HTML file and save CSV alongside it. Convenience function.
    
    Returns the parsed data dict.
    """
    parsed = parse_search_html(html_path)
    if parsed["link_count"] > 0 or parsed["youtube_urls"]:
        save_parsed_csv(html_path, parsed)
    return parsed
