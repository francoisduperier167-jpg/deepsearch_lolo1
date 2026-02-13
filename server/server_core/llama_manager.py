"""server/server_core/llama_manager.py — Start/stop llama-server process."""
import os, subprocess, platform, shutil, asyncio, aiohttp
from pathlib import Path
from config.settings import LLAMA_HOST, LLAMA_PORT, LLAMA_API, BASE_DIR
from server.server_core.state import app_state
from utils.logger import logger

def find_llama_server() -> str:
    found = shutil.which("llama-server") or shutil.which("llama-server.exe")
    if found: return found
    for p in [Path(os.environ.get("USERPROFILE",""))/"llama.cpp"/"build"/"bin"/"Release"/"llama-server.exe",
              Path(os.environ.get("USERPROFILE",""))/"llama.cpp"/"build"/"bin"/"llama-server.exe",
              BASE_DIR/"llama-server.exe", BASE_DIR/"bin"/"llama-server.exe"]:
        if p.exists(): return str(p)
    return ""

async def start_llama(model_key, model_path, gpu_layers, ctx_size, llama_path="") -> dict:
    if not Path(model_path).exists(): return {"error":f"File not found: {model_path}"}
    await stop_llama()
    app_state.active_model=model_key; app_state.model_path=model_path; app_state.gpu_layers=gpu_layers
    exe = llama_path or find_llama_server()
    if not exe: return {"error":"llama-server not found"}
    cmd=[exe,"-m",model_path,"--host",LLAMA_HOST,"--port",str(LLAMA_PORT),"-ngl",str(gpu_layers),
         "-c",str(ctx_size),"--threads",str(max(4,(os.cpu_count() or 4)//2))]
    logger.log(f"Starting: {' '.join(cmd)}")
    try:
        cf = subprocess.CREATE_NO_WINDOW if platform.system()=="Windows" else 0
        app_state.llama_process=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=cf)
        for i in range(60):
            await asyncio.sleep(1)
            if app_state.llama_process.poll() is not None:
                return {"error":f"Crashed: {app_state.llama_process.stderr.read().decode('utf-8',errors='replace')[:300]}"}
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(f"{LLAMA_API}/health",timeout=aiohttp.ClientTimeout(total=2)) as r:
                        if r.status==200: app_state.is_running=True; logger.log("llama-server ready!"); return {"status":"ok"}
            except Exception:
                if i%10==0 and i>0: logger.log(f"Waiting... ({i}s)")
        return {"error":"Timeout 60s"}
    except FileNotFoundError: return {"error":f"Not found: {exe}"}
    except Exception as e: return {"error":str(e)}

async def stop_llama():
    if app_state.llama_process:
        try: app_state.llama_process.terminate(); app_state.llama_process.wait(timeout=5)
        except Exception:
            try: app_state.llama_process.kill()
            except: pass
        app_state.llama_process=None
    app_state.is_running=False; app_state.active_model=None
    logger.log("llama-server stopped")
