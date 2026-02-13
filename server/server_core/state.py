"""server/server_core/state.py — Global application state singleton."""
import subprocess, asyncio
from typing import Optional

class AppState:
    def __init__(self):
        self.llama_process: Optional[subprocess.Popen] = None
        self.active_model: Optional[str] = None
        self.model_path: Optional[str] = None
        self.gpu_layers = 0; self.is_running = False
        self.pipeline = None; self.scan_running = False
        self.scan_task: Optional[asyncio.Task] = None
        self.vram_history = []; self.results = {}; self.resolution_status = {}
        self.progress = {"total_states":50,"completed_states":0,"current_state":"","current_city":"",
            "current_category":"","total_tasks":450,"completed_tasks":0,"resolved_tasks":0,
            "failed_tasks":0,"started_at":None,"eta_seconds":None}
        # Query tracking
        self.query_log = []
        # ── Checkpoint system ──
        self.auto_mode = False          # True = skip all checkpoints, full auto
        self.checkpoint_name = ""       # e.g. "queries_ready", "search_done", "candidates_found"
        self.checkpoint_data = {}       # Data to show user: queries, links, candidates etc.
        self.checkpoint_waiting = False # True = pipeline paused, waiting for user action
        self.checkpoint_response = None # "continue" | "modify" | "skip" | "auto"
        self.checkpoint_modifications = {} # User edits (e.g. modified queries)
        self.checkpoint_event: Optional[asyncio.Event] = None  # Unblocks pipeline

app_state = AppState()
