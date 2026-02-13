"""pipeline/pipeline_ui/progress.py — Progress reporting to UI.
INPUT: event data | OUTPUT: updates app_state in-place
"""
from server.server_core.state import app_state

def progress_callback(data: dict):
    dtype = data.get("type","")
    if dtype == "state_progress":
        app_state.progress["current_state"] = data.get("state","")
    elif dtype == "category_resolved":
        app_state.progress["resolved_tasks"] += 1
        st=data.get("state",""); city=data.get("city",""); cat=data.get("category","")
        ch=data.get("channel",{})
        if st not in app_state.results: app_state.results[st]={}
        if city not in app_state.results[st]: app_state.results[st][city]={}
        app_state.results[st][city][cat]=ch
