"""utils/logger.py — Centralized logging with buffer for UI polling."""
from datetime import datetime
from typing import List

class Logger:
    def __init__(self, max_entries=500):
        self.entries: List[str] = []
        self.max_entries = max_entries
    def log(self, msg: str):
        entry = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
        self.entries.append(entry)
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries:]
        try: print(entry)
        except UnicodeEncodeError: print(entry.encode('ascii',errors='replace').decode('ascii'))
    def get_recent(self, n=150): return self.entries[-n:]
    def clear(self): self.entries.clear()

logger = Logger()
