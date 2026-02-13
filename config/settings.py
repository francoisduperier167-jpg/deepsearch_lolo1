"""config/settings.py — All constants, single source of truth."""
from pathlib import Path
BASE_DIR = Path(__file__).parent.parent.resolve()
WEB_PORT = 8080
LLAMA_HOST = "127.0.0.1"
LLAMA_PORT = 8081
LLAMA_API = f"http://{LLAMA_HOST}:{LLAMA_PORT}"
MODELS = {
    "mistral3_q4": {"name":"Mistral 3 Q4","desc":"4-bit, leger","vram":6,"ngl":35},
    "qwen25_32b_q8": {"name":"Qwen 2.5 32B Q8","desc":"8-bit, precis","vram":24,"ngl":60},
}
MAX_WAVES = 3
PAGES_PER_QUERY = 2
MAX_PAGES_TO_FETCH = 25
MIN_TRIAGE_SCORE = 4
SUB_MIN = 20_000
SUB_MAX = 150_000
MIN_CITY_SCORE = 0.4
MIN_TOTAL_SCORE = 0.5
LLM_TIMEOUT = 180
LLM_TEMP = 0.2
LLM_MAX_TOKENS = 4096
RATE_MIN = 3.0
RATE_MAX = 6.0
RATE_DOMAIN = 8.0
RATE_BRAVE = 12.0  # Brave Search needs more spacing
PENDING = "pending"
IN_PROGRESS = "in_progress"
RESOLVED = "resolved"
PARTIAL = "partial"
FAILED = "failed"
