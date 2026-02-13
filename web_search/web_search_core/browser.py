"""web_search/web_search_core/browser.py — Stealth browser navigation with Playwright Firefox.

Simulates real human browsing:
- Firefox (less fingerprinted than Chrome)
- Random delays, mouse movements, gradual scrolling
- Typing character by character with random intervals
- Realistic viewport, timezone, language
- No webdriver flag exposed
- Saves fully-rendered page as single HTML file

Dependencies: pip install playwright && playwright install firefox
"""
import asyncio
import random
import re
import time
from pathlib import Path
from typing import Optional, Dict, List

from config.settings import BASE_DIR
from utils.logger import logger


# ── Realistic profiles ──
VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 1280, "height": 720},
]

TIMEZONES = ["America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles"]

LOCALES = ["en-US", "en-US", "en-US", "en-GB"]  # Weighted towards US

USER_AGENTS_FF = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
]


def _safe_name(s: str) -> str:
    return re.sub(r'[^\w\s-]', '', s).strip().replace(' ', '_')[:60]


def _results_dir(state: str, city: str, step_name: str = "", query_label: str = "") -> Path:
    """Build nested results directory.
    
    Structure: RESULTATS/{state}/{city}/{step}/{query}/
    """
    d = BASE_DIR / "RESULTATS" / _safe_name(state) / _safe_name(city)
    if step_name:
        d = d / _safe_name(step_name)
    if query_label:
        d = d / _safe_name(query_label)
    d.mkdir(parents=True, exist_ok=True)
    return d


class StealthBrowser:
    """A human-like browser session using Playwright Firefox."""

    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None
        self._playwright = None
        self._profile = None

    async def start(self, proxy: Optional[Dict] = None):
        """Launch Firefox with stealth settings."""
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._profile = {
            "viewport": random.choice(VIEWPORTS),
            "timezone": random.choice(TIMEZONES),
            "locale": random.choice(LOCALES),
            "user_agent": random.choice(USER_AGENTS_FF),
        }

        launch_args = [
            "-purgecaches",
        ]

        browser_opts = {
            "headless": True,
            "firefox_user_prefs": {
                # Disable webdriver detection
                "dom.webdriver.enabled": False,
                "useAutomationExtension": False,
                # Realistic settings
                "media.navigator.enabled": False,
                "privacy.resistFingerprinting": False,
                "general.platform.override": "Win32",
                "general.appversion.override": "5.0 (Windows)",
                "network.http.referer.XOriginPolicy": 0,
                # Performance
                "network.http.pipelining": True,
                "network.http.max-connections-per-server": 6,
            },
            "args": launch_args,
        }

        if proxy:
            browser_opts["proxy"] = proxy

        self.browser = await self._playwright.firefox.launch(**browser_opts)

        context_opts = {
            "viewport": self._profile["viewport"],
            "locale": self._profile["locale"],
            "timezone_id": self._profile["timezone"],
            "user_agent": self._profile["user_agent"],
            "accept_downloads": False,
            "java_script_enabled": True,
            "ignore_https_errors": True,
        }

        self.context = await self.browser.new_context(**context_opts)

        # Block unnecessary resources for speed
        await self.context.route("**/*.{png,jpg,jpeg,gif,svg,ico,woff,woff2,ttf}", 
                                  lambda route: route.abort())

        self.page = await self.context.new_page()

        # Remove webdriver traces from navigator
        await self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            window.chrome = undefined;
        """)

        logger.log(f"[BROWSER] Firefox started — {self._profile['viewport']['width']}x{self._profile['viewport']['height']} | {self._profile['timezone']}")

    async def close(self):
        """Close browser."""
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass
        self.browser = None
        self.context = None
        self.page = None

    # ── Human-like actions ──

    async def _human_delay(self, min_s=0.5, max_s=2.0):
        """Random delay simulating human hesitation."""
        await asyncio.sleep(random.uniform(min_s, max_s))

    async def _human_type(self, selector: str, text: str):
        """Type text character by character with random delays."""
        el = await self.page.query_selector(selector)
        if not el:
            return
        await el.click()
        await self._human_delay(0.2, 0.5)
        for char in text:
            await self.page.keyboard.type(char, delay=random.randint(30, 120))
            # Occasional longer pause (thinking)
            if random.random() < 0.05:
                await self._human_delay(0.3, 0.8)

    async def _human_scroll(self, distance: int = 0):
        """Scroll down gradually like a human reading."""
        if distance <= 0:
            distance = random.randint(800, 2500)
        steps = random.randint(3, 8)
        per_step = distance // steps
        for _ in range(steps):
            await self.page.mouse.wheel(0, per_step + random.randint(-30, 30))
            await self._human_delay(0.2, 0.6)

    async def _move_mouse_random(self):
        """Move mouse to a random position on the page."""
        vp = self._profile["viewport"]
        x = random.randint(100, vp["width"] - 100)
        y = random.randint(100, vp["height"] - 100)
        await self.page.mouse.move(x, y, steps=random.randint(5, 15))

    # ── Navigation ──

    async def navigate(self, url: str, wait_for: str = "networkidle", timeout: int = 30000) -> bool:
        """Navigate to URL with human-like behavior."""
        try:
            await self._move_mouse_random()
            await self._human_delay(0.3, 1.0)
            resp = await self.page.goto(url, wait_until=wait_for, timeout=timeout)
            if resp and resp.status >= 400:
                logger.log(f"[BROWSER] HTTP {resp.status} for {url[:60]}")
                return False
            # Wait a bit more for JS to settle
            await self._human_delay(1.0, 2.5)
            # Scroll down a bit like reading
            await self._human_scroll(random.randint(300, 600))
            return True
        except Exception as e:
            logger.log(f"[BROWSER] Navigate error: {str(e)[:80]}")
            return False

    async def search_google(self, query: str, page_num: int = 0) -> bool:
        """Perform a Google search like a human."""
        if page_num == 0:
            # Go to google.com first
            ok = await self.navigate("https://www.google.com", wait_for="domcontentloaded")
            if not ok:
                return False
            await self._human_delay(1.0, 2.0)

            # Handle consent popup if present
            try:
                accept = await self.page.query_selector('button:has-text("Accept"), button:has-text("Accepter"), button:has-text("I agree")')
                if accept:
                    await accept.click()
                    await self._human_delay(1.0, 2.0)
            except Exception:
                pass

            # Type search query
            search_sel = 'textarea[name="q"], input[name="q"]'
            await self._human_type(search_sel, query)
            await self._human_delay(0.3, 0.8)

            # Press Enter
            await self.page.keyboard.press("Enter")
            await self._human_delay(2.0, 4.0)
            try:
                await self.page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
        else:
            # Click "Next" or navigate to page
            try:
                next_btn = await self.page.query_selector('a#pnnext, a[aria-label="Next"], td.d6cvqb a')
                if next_btn:
                    await self._human_delay(1.0, 2.0)
                    await next_btn.click()
                    await self._human_delay(2.0, 4.0)
                    try:
                        await self.page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        pass
                else:
                    return False
            except Exception:
                return False

        await self._human_scroll(random.randint(500, 1500))
        return True

    async def search_brave(self, query: str, page_num: int = 0) -> bool:
        """Perform a Brave Search like a human."""
        if page_num == 0:
            ok = await self.navigate("https://search.brave.com", wait_for="domcontentloaded")
            if not ok:
                return False
            await self._human_delay(1.0, 2.0)

            search_sel = 'input#searchbox, input[name="q"]'
            await self._human_type(search_sel, query)
            await self._human_delay(0.3, 0.8)
            await self.page.keyboard.press("Enter")
            await self._human_delay(2.0, 4.0)
            try:
                await self.page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
        else:
            # Click next page
            try:
                next_btn = await self.page.query_selector('a.btn--pagination:has-text("Next"), a[aria-label="Next page"]')
                if not next_btn:
                    # Try generic pagination
                    next_btn = await self.page.query_selector(f'a.pagination-item[href*="offset"]')
                if next_btn:
                    await self._human_delay(1.0, 2.0)
                    await next_btn.click()
                    await self._human_delay(2.0, 4.0)
                    try:
                        await self.page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        pass
                else:
                    return False
            except Exception:
                return False

        await self._human_scroll(random.randint(500, 1500))
        return True

    # ── Save page ──

    async def save_page_html(self, output_path: Path) -> Dict:
        """Save the current page as a clean single HTML file.
        
        Gets the fully rendered DOM (after JS execution), 
        inlines essential styles, removes scripts.
        """
        try:
            # Get the fully rendered HTML
            html = await self.page.content()
            
            # Get the page title
            title = await self.page.title()
            
            # Get current URL
            url = self.page.url

            # Clean the HTML: remove scripts, keep structure
            # This is our "SingleFile-like" flatten — we keep CSS inline but strip JS
            clean_html = self._flatten_html(html, title, url)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(clean_html, encoding='utf-8')

            size_kb = output_path.stat().st_size / 1024
            return {"success": True, "path": str(output_path), "size_kb": round(size_kb, 1), "title": title, "url": url}

        except Exception as e:
            return {"success": False, "path": str(output_path), "error": str(e)[:200]}

    def _flatten_html(self, html: str, title: str, url: str) -> str:
        """Flatten HTML into a single clean file.
        
        - Removes <script> tags (we don't need JS for parsing)
        - Keeps <style> and inline styles (preserves layout for debugging)
        - Adds metadata comment with source URL and timestamp
        """
        import time as _time

        # Remove script tags and their content
        clean = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        # Remove noscript wrappers but keep content
        clean = re.sub(r'</?noscript[^>]*>', '', clean, flags=re.IGNORECASE)
        # Remove event handlers
        clean = re.sub(r'\s+on\w+="[^"]*"', '', clean)
        clean = re.sub(r"\s+on\w+='[^']*'", '', clean)

        # Add source metadata
        meta = f"""<!-- 
  YouTube Scout v2 — Saved search result page
  Source: {url}
  Title: {title}
  Saved: {_time.strftime('%Y-%m-%d %H:%M:%S')}
-->
"""
        # Insert after <head> or at start
        if '<head' in clean.lower():
            clean = re.sub(r'(<head[^>]*>)', r'\1\n' + meta, clean, count=1, flags=re.IGNORECASE)
        else:
            clean = meta + clean

        return clean


async def search_and_save(query: str, state: str, city: str, category: str,
                          engine: str = "brave", page_num: int = 0,
                          step_name: str = "", query_num: int = 0,
                          browser: Optional[StealthBrowser] = None,
                          log_func=None) -> Dict:
    """Execute a search and save the results page as HTML.
    
    Saves to: RESULTATS/{state}/{city}/{step_name}/Requete_{query_num}_{query}/
    
    Args:
        query: Search query string
        state, city, category: For file organization
        engine: "google" or "brave"
        page_num: Page number (0 = first page)
        step_name: e.g. "Etape_1_Recherche_directe"
        query_num: e.g. 1, 2, 3
        browser: Existing StealthBrowser instance (reused for session)
        log_func: Logging function
    
    Returns: {
        "success": bool,
        "html_path": str,
        "engine": str,
        "query": str,
        "page_num": int,
        "title": str,
        "url": str,
    }
    """
    log = log_func or logger.log
    own_browser = False

    if not browser:
        browser = StealthBrowser()
        await browser.start()
        own_browser = True

    try:
        # Perform search
        if engine == "google":
            ok = await browser.search_google(query, page_num)
        else:
            ok = await browser.search_brave(query, page_num)

        if not ok:
            return {"success": False, "html_path": "", "engine": engine, "query": query,
                    "page_num": page_num, "error": "Search navigation failed"}

        # Build folder: RESULTATS/State/City/Etape_N/Requete_N_query/
        query_label = f"Requete_{query_num}_{_safe_name(query[:40])}" if query_num else _safe_name(query[:40])
        results_dir = _results_dir(state, city, step_name, query_label)

        # Filename: engine_pN.html
        filename = f"{engine}_p{page_num + 1}.html"
        output_path = results_dir / filename

        # Save page
        result = await browser.save_page_html(output_path)

        if result["success"]:
            log(f"        [{engine.upper()}] Saved: {filename} ({result['size_kb']} KB)")
        else:
            log(f"        [{engine.upper()}] Save failed: {result.get('error', '')[:60]}")

        return {
            "success": result["success"],
            "html_path": result.get("path", ""),
            "engine": engine,
            "query": query,
            "page_num": page_num,
            "title": result.get("title", ""),
            "url": result.get("url", ""),
            "size_kb": result.get("size_kb", 0),
        }

    finally:
        if own_browser:
            await browser.close()


def check_browser_available() -> Dict:
    """Check if Playwright and Firefox are installed."""
    info = {"playwright_installed": False, "firefox_installed": False, "error": ""}
    try:
        import playwright
        info["playwright_installed"] = True
    except ImportError:
        info["error"] = "playwright not installed. Run: pip install playwright && playwright install firefox"
        return info

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.firefox.launch(headless=True)
            browser.close()
            info["firefox_installed"] = True
    except Exception as e:
        info["error"] = f"Firefox not available: {str(e)[:100]}. Run: playwright install firefox"

    return info
