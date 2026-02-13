"""server/server.py — Creates and configures the aiohttp web application."""
from aiohttp import web
from config.settings import WEB_PORT
from server.server_ui.routes import (h_index, h_status, h_start_model, h_stop_model,
    h_start_scan, h_stop_scan, h_results, h_export, h_logs, h_queries,
    h_strategy_get, h_strategy_save, h_check_tools,
    h_models_list, h_models_add, h_models_delete, h_vram_purge,
    h_checkpoint_status, h_checkpoint_respond, h_set_auto_mode,
    h_graph_stats, h_graph_criteria_get, h_graph_criteria_set,
    h_graph_entities, h_graph_targets, h_graph_score_detail,
    h_graph_export, h_graph_tasks,
    h_cost_summary, h_cost_curve, h_cost_log, h_cost_config,
    h_planner_analyze, h_planner_plan, h_planner_queries)

def create_app():
    app = web.Application()
    app.router.add_get("/", h_index)
    app.router.add_get("/api/status", h_status)
    app.router.add_post("/api/model/start", h_start_model)
    app.router.add_post("/api/model/stop", h_stop_model)
    app.router.add_post("/api/scan/start", h_start_scan)
    app.router.add_post("/api/scan/stop", h_stop_scan)
    app.router.add_get("/api/results", h_results)
    app.router.add_get("/api/export", h_export)
    app.router.add_get("/api/logs", h_logs)
    app.router.add_get("/api/queries", h_queries)
    app.router.add_get("/api/strategy", h_strategy_get)
    app.router.add_post("/api/strategy", h_strategy_save)
    app.router.add_get("/api/check-tools", h_check_tools)
    app.router.add_get("/api/models/list", h_models_list)
    app.router.add_post("/api/models/add", h_models_add)
    app.router.add_post("/api/models/delete", h_models_delete)
    app.router.add_post("/api/vram/purge", h_vram_purge)
    app.router.add_get("/api/checkpoint", h_checkpoint_status)
    app.router.add_post("/api/checkpoint/respond", h_checkpoint_respond)
    app.router.add_post("/api/auto-mode", h_set_auto_mode)
    # Graph scorer
    app.router.add_get("/api/graph/stats", h_graph_stats)
    app.router.add_get("/api/graph/criteria", h_graph_criteria_get)
    app.router.add_post("/api/graph/criteria", h_graph_criteria_set)
    app.router.add_get("/api/graph/entities", h_graph_entities)
    app.router.add_get("/api/graph/targets", h_graph_targets)
    app.router.add_get("/api/graph/score", h_graph_score_detail)
    app.router.add_get("/api/graph/export", h_graph_export)
    app.router.add_get("/api/graph/tasks", h_graph_tasks)
    # Cost engine
    app.router.add_get("/api/cost/summary", h_cost_summary)
    app.router.add_get("/api/cost/curve", h_cost_curve)
    app.router.add_get("/api/cost/log", h_cost_log)
    app.router.add_get("/api/cost/config", h_cost_config)
    app.router.add_post("/api/cost/config", h_cost_config)
    # Planner
    app.router.add_post("/api/planner/analyze", h_planner_analyze)
    app.router.add_get("/api/planner/plan", h_planner_plan)
    app.router.add_get("/api/planner/queries", h_planner_queries)
    return app
