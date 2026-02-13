"""server/server_core/llm_client.py — Send prompts to llama.cpp server.

Two interfaces:
  query_llm(prompt, system) → dict|None   — For pipeline (returns parsed JSON)
  query_llm_raw(prompt, system) → str     — For strategy_planner (returns raw text)

Features: retry with backoff (3 attempts), custom system prompts, error logging.
"""
import asyncio
import aiohttp
from typing import Optional
from config.settings import LLAMA_API, LLM_TIMEOUT, LLM_TEMP, LLM_MAX_TOKENS
from utils.json_extract import extract_json
from utils.logger import logger

MAX_RETRIES = 3
RETRY_DELAYS = [2, 5, 10]


async def _call_llm(prompt: str, system: str = "", timeout: int = LLM_TIMEOUT) -> Optional[str]:
    """Low-level LLM call. Returns raw text or None. Retries on failure."""
    if not system:
        system = "You are a research assistant. Respond with valid JSON only. No markdown."

    chat = {"model": "local", "messages": [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt}
    ], "temperature": LLM_TEMP, "max_tokens": LLM_MAX_TOKENS}

    comp = {"prompt": f"[INST] <<SYS>>{system}<</SYS>>\n\n{prompt} [/INST]",
            "n_predict": LLM_MAX_TOKENS, "temperature": LLM_TEMP,
            "top_p": 0.9, "stop": ["\n\n\n"], "stream": False}

    last_error = ""
    for attempt in range(MAX_RETRIES):
        try:
            async with aiohttp.ClientSession() as s:
                try:
                    async with s.post(f"{LLAMA_API}/v1/chat/completions", json=chat,
                        timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                        if r.status == 200:
                            d = await r.json()
                            return d["choices"][0]["message"]["content"]
                        last_error = f"chat HTTP {r.status}"
                except (aiohttp.ClientError, asyncio.TimeoutError, KeyError) as e:
                    last_error = f"chat: {str(e)[:80]}"
                try:
                    async with s.post(f"{LLAMA_API}/completion", json=comp,
                        timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                        if r.status == 200:
                            d = await r.json()
                            return d.get("content", "")
                        last_error = f"comp HTTP {r.status}"
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    last_error = f"comp: {str(e)[:80]}"
        except Exception as e:
            last_error = str(e)[:100]

        if attempt < MAX_RETRIES - 1:
            delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
            logger.log(f"[LLM] Retry {attempt+1}/{MAX_RETRIES} in {delay}s — {last_error}")
            await asyncio.sleep(delay)

    logger.log(f"[LLM ERROR] {MAX_RETRIES} attempts failed: {last_error}")
    logger.log(f"[LLM ERROR] Prompt: {prompt[:120]}...")
    return None


async def query_llm(prompt: str, system: str = "", timeout: int = LLM_TIMEOUT) -> Optional[dict]:
    """Send prompt, return parsed JSON dict. Used by pipeline modules."""
    raw = await _call_llm(prompt, system=system, timeout=timeout)
    if raw is None:
        return None
    result = extract_json(raw)
    if result is None:
        logger.log(f"[LLM] JSON parse failed. Raw: {raw[:200]}")
    return result


async def query_llm_raw(prompt: str, system: str = "", timeout: int = LLM_TIMEOUT) -> str:
    """Send prompt, return raw text. Used by strategy_planner."""
    raw = await _call_llm(prompt, system=system, timeout=timeout)
    return raw or ""
