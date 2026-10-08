"""Dashboard backend: start runs, poll events, answer approvals, reset the mock environment."""
import threading
import time
import urllib.request
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import config
from agent.events import EventBus
from agent.runner import run_task

app = FastAPI()
STATE = {"bus": None}
config.RUNS_DIR.mkdir(exist_ok=True)
app.mount("/runs", StaticFiles(directory=str(config.RUNS_DIR)), name="runs")


class RunReq(BaseModel):
    task: str


class RespondReq(BaseModel):
    answer: str


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "index.html")


@app.get("/api/config")
def get_config():
    return {"provider": config.llm_provider() or None, "threshold": config.APPROVAL_THRESHOLD,
            "portal": config.PORTAL_URL, "finance": config.FINANCE_URL}


@app.post("/api/run")
def start(req: RunReq):
    bus = STATE["bus"]
    if bus and bus.status == "running":
        return JSONResponse({"error": "A task is already running."}, status_code=409)
    bus = EventBus(time.strftime("%Y%m%d-%H%M%S"))
    STATE["bus"] = bus

    def work():
        try:
            run_task(req.task.strip(), bus)
        except Exception as e:  # noqa: BLE001
            bus.emit("final", status="failed", summary=str(e), evidence=[], verified=False)
            bus.status = "done"

    threading.Thread(target=work, daemon=True).start()
    return {"run_id": bus.run_id}


@app.get("/api/events")
def events(after: int = 0):
    bus = STATE["bus"]
    if not bus:
        return {"run_id": None, "status": "idle", "pending": None, "events": []}
    return {"run_id": bus.run_id, "status": bus.status, "pending": bus.pending, "events": bus.since(after)}


@app.post("/api/respond")
def respond(req: RespondReq):
    bus = STATE["bus"]
    return {"ok": bool(bus and bus.respond(req.answer))}


@app.post("/api/reset")
def reset_env():
    r = urllib.request.Request(f"{config.FINANCE_URL}/admin/reset", method="POST")
    urllib.request.urlopen(r, timeout=5).read()
    return {"ok": True}
