"""utils/rate_limiter.py — Per-domain + global rate limiting."""
import asyncio, time, random
from typing import Dict
from config.settings import RATE_MIN, RATE_MAX, RATE_DOMAIN, RATE_BRAVE

class RateLimiter:
    def __init__(self):
        self.last_global = 0.0
        self.domain_times: Dict[str,float] = {}
        self.total_requests = 0
        self.lock = asyncio.Lock()

    async def wait(self, domain=""):
        async with self.lock:
            now = time.time()
            # Global delay
            target = random.uniform(RATE_MIN, RATE_MAX)
            if now - self.last_global < target:
                await asyncio.sleep(target - (now - self.last_global))
            # Per-domain delay (higher for Brave Search)
            if domain:
                delay = RATE_BRAVE if 'brave' in domain else RATE_DOMAIN
                last = self.domain_times.get(domain, 0)
                elapsed = time.time() - last
                if elapsed < delay:
                    jitter = random.uniform(0, 2.0)
                    await asyncio.sleep(delay - elapsed + jitter)
                self.domain_times[domain] = time.time()
            self.last_global = time.time()
            self.total_requests += 1

rate_limiter = RateLimiter()
