"""server/server_ui/routes.py — All HTTP API endpoints."""
import time, json, asyncio
from pathlib import Path
from datetime import datetime
from aiohttp import web
from config.settings import MODELS, BASE_DIR
from server.server_core.state import app_state
from server.server_core.gpu_monitor import get_gpu_info, get_system_info
from server.server_core.llama_manager import find_llama_server, start_llama, stop_llama
from server.server_core.llm_client import query_llm, query_llm_raw
from pipeline.pipeline import run_full_scan
from utils.logger import logger

async def h_index(req):
    return web.FileResponse(Path(__file__).parent / "index.html")

async def h_status(req):
    gpu=get_gpu_info(); si=get_system_info()
    app_state.vram_history.append({"t":time.time(),"used":gpu["used_mb"],"total":gpu["total_mb"]})
    if len(app_state.vram_history)>300: app_state.vram_history=app_state.vram_history[-300:]
    return web.json_response({"model":{"active":app_state.active_model,
        "name":MODELS.get(app_state.active_model,{}).get("name","None"),
        "server_running":app_state.is_running,"model_path":app_state.model_path},
        "gpu":gpu,"system":si,"scan":{"running":app_state.scan_running,"progress":app_state.progress},
        "vram_history":app_state.vram_history[-60:],"models_available":MODELS,
        "llama_server_found":find_llama_server(),
        "results_count":app_state.progress.get("resolved_tasks",0),
        "resolution_status":app_state.resolution_status})

async def h_start_model(req):
    d=await req.json()
    mk=d.get("model"); mp=d.get("model_path","").strip()
    ngl=int(d.get("gpu_layers",35)); ctx=int(d.get("ctx_size",4096))
    lp=d.get("llama_server_path","").strip()
    if mk not in MODELS: return web.json_response({"error":"Unknown model"},status=400)
    if not mp: return web.json_response({"error":"Model path required"},status=400)
    r=await start_llama(mk,mp,ngl,ctx,lp)
    if "error" in r: return web.json_response(r,status=500)
    return web.json_response(r)

async def h_stop_model(req):
    await stop_llama(); return web.json_response({"status":"ok"})

async def h_start_scan(req):
    if not app_state.is_running: return web.json_response({"error":"No model active"},status=400)
    if app_state.scan_running: return web.json_response({"error":"Scan already running"},status=400)
    app_state.scan_task=asyncio.create_task(run_full_scan())
    return web.json_response({"status":"ok"})

async def h_stop_scan(req):
    app_state.scan_running=False
    if app_state.pipeline: app_state.pipeline.stop()
    return web.json_response({"status":"ok"})

async def h_results(req):
    return web.json_response({"results":app_state.results,"categories":{"cinema":"Cinema / Movie Reviews",
        "gaming":"Gaming / Video Games","culture_entertainment":"Culture & Entertainment"},
        "resolution":app_state.resolution_status})

async def h_export(req):
    p=BASE_DIR/"results.json"
    if p.exists(): return web.FileResponse(p,headers={"Content-Disposition":"attachment; filename=results.json"})
    return web.json_response({"error":"No file"},status=404)

async def h_logs(req):
    return web.json_response({"logs":logger.get_recent(150)})

async def h_queries(req):
    """Return recent query log for UI display."""
    return web.json_response({"queries": app_state.query_log[-100:]})

# ── Saved models management ──
SAVED_MODELS_FILE = BASE_DIR / "saved_models.json"

def _load_saved_models():
    if SAVED_MODELS_FILE.exists():
        try:
            return json.loads(SAVED_MODELS_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return []

def _save_saved_models(models):
    SAVED_MODELS_FILE.write_text(json.dumps(models, indent=2, ensure_ascii=False), encoding='utf-8')

async def h_models_list(req):
    """List saved models."""
    return web.json_response({"models": _load_saved_models()})

async def h_models_add(req):
    """Add/update a saved model."""
    d = await req.json()
    name = d.get("name","").strip()
    path = d.get("path","").strip()
    if not name or not path:
        return web.json_response({"error": "name and path required"}, status=400)
    models = _load_saved_models()
    # Update existing or add new
    found = False
    for m in models:
        if m["name"] == name:
            m["path"] = path
            m.update({k:v for k,v in d.items() if k in ("ngl","ctx","preset")})
            found = True; break
    if not found:
        models.append({"name": name, "path": path, 
                        "ngl": d.get("ngl", 35), "ctx": d.get("ctx", 4096),
                        "preset": d.get("preset", "mistral3_q4"),
                        "added": datetime.now().isoformat()})
    _save_saved_models(models)
    return web.json_response({"status": "ok", "models": models})

async def h_models_delete(req):
    """Delete a saved model by name."""
    d = await req.json()
    name = d.get("name","").strip()
    models = _load_saved_models()
    models = [m for m in models if m["name"] != name]
    _save_saved_models(models)
    return web.json_response({"status": "ok", "models": models})

# ── VRAM purge ──
async def h_vram_purge(req):
    """Stop llama-server and try to free VRAM."""
    import subprocess, platform
    # First stop our own llama-server
    await stop_llama()
    logger.log("[VRAM] Stopping llama-server...")
    
    freed = False
    if platform.system() == "Windows":
        # Kill any llama-server processes
        for proc_name in ["llama-server.exe", "llama-server.EXE", "llama-cli.exe"]:
            try:
                subprocess.run(["taskkill", "/F", "/IM", proc_name], 
                             capture_output=True, timeout=5)
                freed = True
            except Exception:
                pass
        # Try nvidia-smi reset if available
        try:
            r = subprocess.run(["nvidia-smi", "--gpu-reset"], capture_output=True, timeout=10)
            if r.returncode == 0:
                logger.log("[VRAM] nvidia-smi GPU reset done")
        except Exception:
            pass
    else:
        # Linux: kill llama processes
        try:
            subprocess.run(["pkill", "-f", "llama-server"], capture_output=True, timeout=5)
            freed = True
        except Exception:
            pass
    
    # Wait a bit for memory to be released
    import asyncio
    await asyncio.sleep(2)
    
    gpu = get_gpu_info()
    logger.log(f"[VRAM] After purge: {gpu['used_mb']:.0f} / {gpu['total_mb']:.0f} MB")
    return web.json_response({"status": "ok", "gpu": gpu})

async def h_strategy_get(req):
    """Return current strategy text."""
    from config.strategy import load_strategy
    return web.json_response({"strategy": load_strategy()})

async def h_strategy_save(req):
    """Save updated strategy text."""
    from config.strategy import save_strategy
    d = await req.json()
    text = d.get("strategy", "")
    if not text:
        return web.json_response({"error": "Empty strategy"}, status=400)
    save_strategy(text)
    logger.log("[STRATEGY] Updated by user")
    return web.json_response({"status": "ok"})

async def h_check_tools(req):
    """Check if Playwright and Firefox are available."""
    from web_search.web_search_core.browser import check_browser_available
    info = check_browser_available()
    return web.json_response(info)

# ── Checkpoint endpoints ──

async def h_checkpoint_status(req):
    """Get current checkpoint state."""
    return web.json_response({
        "waiting": app_state.checkpoint_waiting,
        "name": app_state.checkpoint_name,
        "data": app_state.checkpoint_data,
        "auto_mode": app_state.auto_mode,
    })

async def h_checkpoint_respond(req):
    """User responds to a checkpoint: continue, modify, skip, or switch to auto."""
    d = await req.json()
    action = d.get("action", "continue")  # continue | modify | skip | auto
    
    if action == "auto":
        app_state.auto_mode = True
        app_state.checkpoint_response = "continue"
        logger.log("[CHECKPOINT] Switched to FULL AUTO mode")
    elif action == "modify":
        app_state.checkpoint_response = "modify"
        app_state.checkpoint_modifications = d.get("modifications", {})
        logger.log(f"[CHECKPOINT] User modified: {list(app_state.checkpoint_modifications.keys())}")
    elif action == "skip":
        app_state.checkpoint_response = "skip"
        logger.log("[CHECKPOINT] User skipped this step")
    else:
        app_state.checkpoint_response = "continue"
        logger.log("[CHECKPOINT] User validated, continuing...")
    
    app_state.checkpoint_waiting = False
    # Unblock the pipeline
    if app_state.checkpoint_event:
        app_state.checkpoint_event.set()
    
    return web.json_response({"status": "ok", "action": action})

async def h_set_auto_mode(req):
    """Toggle auto mode on/off."""
    d = await req.json()
    app_state.auto_mode = d.get("auto", False)
    logger.log(f"[MODE] {'FULL AUTO' if app_state.auto_mode else 'VALIDATION'}")
    return web.json_response({"auto_mode": app_state.auto_mode})

# ── Graph Scorer API ──

def _graph():
    from pipeline.pipeline_core.graph_scorer import GraphScorer
    return GraphScorer()

async def h_graph_stats(req):
    return web.json_response(_graph().get_stats())

async def h_graph_criteria_get(req):
    g = _graph()
    return web.json_response({"criteria": g.get_criteria(), "threshold": g.get_threshold()})

async def h_graph_criteria_set(req):
    d = await req.json()
    g = _graph()
    g.configure_criteria(d.get("criteria", []), d.get("threshold", 60))
    return web.json_response({"status": "ok"})

async def h_graph_entities(req):
    g = _graph()
    status = req.query.get("status", "")
    city = req.query.get("city", "")
    return web.json_response({"entities": g.find_entities(status=status, city=city)})

async def h_graph_targets(req):
    g = _graph()
    platform = req.query.get("platform", "")
    validated = req.query.get("validated")
    val = None if validated is None else validated == "1"
    return web.json_response({"targets": g.find_targets(platform=platform, validated=val)})

async def h_graph_score_detail(req):
    g = _graph()
    tid = int(req.query.get("target_id", 0))
    if not tid:
        return web.json_response({"error": "target_id required"}, status=400)
    target = g.get_target(tid)
    score = g.get_score(tid)
    entity = g.get_entity(target["entity_id"]) if target and target.get("entity_id") else None
    return web.json_response({"target": target, "score": score, "entity": entity})

async def h_graph_export(req):
    g = _graph()
    fmt = req.query.get("format", "json")
    validated_only = req.query.get("validated", "1") == "1"
    data = g.export_validated() if validated_only else g.export_all()
    if fmt == "csv":
        import csv, io
        if not data:
            return web.Response(text="No data", content_type="text/plain")
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=[k for k in data[0].keys() if k != "raw_data"])
        writer.writeheader()
        for row in data:
            row.pop("raw_data", None)
            if isinstance(row.get("score_details"), dict):
                row["score_details"] = json.dumps(row["score_details"])
            if isinstance(row.get("keywords"), list):
                row["keywords"] = ", ".join(row["keywords"])
            writer.writerow(row)
        return web.Response(text=output.getvalue(), content_type="text/csv",
                           headers={"Content-Disposition": "attachment; filename=scout_export.csv"})
    return web.json_response({"results": data, "count": len(data)})

async def h_graph_tasks(req):
    g = _graph()
    status = req.query.get("status", "")
    return web.json_response({"tasks": g.get_tasks(status=status)})

# ── Cost Engine API ──

def _cost_engine():
    from pipeline.pipeline_core.cost_engine import CostEngine
    try:
        return CostEngine.load()
    except Exception:
        return CostEngine()

async def h_cost_summary(req):
    return web.json_response(_cost_engine().summary())

async def h_cost_curve(req):
    return web.json_response({"curve": _cost_engine().get_efficiency_curve()})

async def h_cost_log(req):
    n = int(req.query.get("n", "50"))
    return web.json_response({"log": _cost_engine().get_log(n)})

async def h_cost_config(req):
    """Get or set cost engine configuration."""
    if req.method == "POST":
        d = await req.json()
        from pipeline.pipeline_core.cost_engine import CostEngine
        engine = CostEngine(
            target_count=d.get("target_count", 10),
            patience_initial=d.get("patience_initial", 30),
            patience_recharge=d.get("patience_recharge", 20),
            patience_drain=d.get("patience_drain", 1),
            epsilon=d.get("epsilon", 0.10),
            min_roi=d.get("min_roi", 0.05),
            global_budget=d.get("global_budget", 500),
        )
        for src in d.get("sources", []):
            engine.add_source(src["name"], src.get("priority", 50))
        engine.save()
        return web.json_response({"status": "ok"})
    else:
        return web.json_response(_cost_engine().to_dict())

# ── Strategy Planner API ──

async def h_planner_analyze(req):
    """Analyze a research prompt into WHO/WHERE/WHAT dimensions."""
    from pipeline.pipeline_core.strategy_planner import StrategyPlanner
    d = await req.json()
    prompt = d.get("prompt", "").strip()
    if not prompt:
        return web.json_response({"error": "prompt required"}, status=400)
    
    planner = StrategyPlanner(llm_func=query_llm_raw)
    try:
        analysis = await planner.analyze(prompt)
        strategies = await planner.build_strategies(analysis)
        path = planner.save_plan()
        
        return web.json_response({
            "analysis": analysis.to_dict(),
            "strategies": [s.to_dict() for s in strategies],
            "query_counts": planner.count_queries(),
            "plan_text": planner.format_plan_text(),
            "saved_to": path,
        })
    except Exception as e:
        logger.log(f"[PLANNER] Error: {str(e)[:200]}")
        return web.json_response({"error": str(e)[:200]}, status=500)

async def h_planner_plan(req):
    """Get the last saved plan."""
    from pipeline.pipeline_core.strategy_planner import StrategyPlanner
    plan = StrategyPlanner.load_plan()
    if not plan:
        return web.json_response({"error": "No plan saved yet"}, status=404)
    return web.json_response(plan)

async def h_planner_queries(req):
    """Get flattened queries for a city/state from the saved plan."""
    from pipeline.pipeline_core.strategy_planner import StrategyPlanner
    city = req.query.get("city", "")
    state = req.query.get("state", "")
    plan = StrategyPlanner.load_plan()
    if not plan or not plan.get("strategies"):
        return web.json_response({"error": "No plan"}, status=404)
    
    # Rebuild planner from saved data and flatten
    planner = StrategyPlanner()
    strategies = []
    from pipeline.pipeline_core.strategy_planner import Strategy
    for s_data in plan["strategies"]:
        strat = Strategy(
            name=s_data["name"], tier=s_data["tier"],
            tier_label=s_data.get("tier_label",""),
            description=s_data.get("description",""),
        )
        strat.steps = planner._parse_steps(s_data.get("steps", []))
        strategies.append(strat)
    
    flat = planner.flatten_queries(strategies, city=city, state=state)
    return web.json_response({"queries": flat, "count": len(flat)})
