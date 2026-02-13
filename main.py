#!/usr/bin/env python3
"""
main.py — YouTube Scout v2 entry point.
Imports server and starts it. Zero logic here.
"""
import sys, platform

if platform.system() == "Windows":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception: pass
    import asyncio
    if sys.version_info >= (3, 8):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from server.server import create_app, WEB_PORT
from aiohttp import web

def main():
    print("=" * 60)
    print("  YouTube Scout v2 — Intelligent Channel Finder")
    print(f"  Interface: http://localhost:{WEB_PORT}")
    print(f"  Platform:  {platform.system()} {platform.release()}")
    print("=" * 60)
    web.run_app(create_app(), host="0.0.0.0", port=WEB_PORT)

if __name__ == "__main__":
    main()
