"""
Local server for the virtual mine-subsidence simulator.

    python virtual_simulator/backend/app.py                 # then open http://127.0.0.1:8000
    python virtual_simulator/backend/app.py --port 8080 --no-browser

REST (control)                          WebSocket /ws (live push, ~5 Hz)
  GET  /api/info                          {"type": "hello", info, snapshot, history, events}   on connect
  GET  /api/state                         {"type": "state", snapshot..., samples: [...], events: [...]}
  POST /api/set     {node, tilt?, vib?, disp?}
  POST /api/preset  {name: normal | vibration_only | full_progression | reset}
  POST /api/speed   {speed: 1 | 2 | 4}

All model behaviour comes from hardware_integration/ (see engine.py). This file is only transport.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import threading
import time
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))   # `python virtual_simulator/backend/app.py` from anywhere

import uvicorn                                                     # noqa: E402
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect   # noqa: E402
from fastapi.responses import FileResponse                        # noqa: E402
from fastapi.staticfiles import StaticFiles                       # noqa: E402
from pydantic import BaseModel, Field                             # noqa: E402

from engine import LIMITS, NODES, Simulator                       # noqa: E402

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
TICK_S = 0.2                                                      # wall-clock push interval

sim: Simulator | None = None
clients: set[WebSocket] = set()


class SetBody(BaseModel):
    node: int
    tilt: float | None = Field(default=None, description="degrees")
    vib: float | None = Field(default=None, description="g, model scale, added to the resting level")
    disp: float | None = Field(default=None, description="mm")


class PresetBody(BaseModel):
    name: str


class SpeedBody(BaseModel):
    speed: float


def _state_msg(samples=None, events=None) -> dict:
    return {"type": "state", **sim.snapshot(), "samples": samples or [], "events": events or []}


async def _broadcast(msg: dict):
    if not clients:
        return
    text = json.dumps(msg)
    dead = []
    for ws in list(clients):
        try:
            await ws.send_text(text)
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.discard(ws)


async def _ticker():
    last = time.monotonic()
    while True:
        await asyncio.sleep(TICK_S)
        now = time.monotonic()
        sim.advance_wall(now - last)
        last = now
        samples, events = sim.drain()
        await _broadcast(_state_msg(samples, events))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global sim
    print("Loading model and calibrating the 3 virtual nodes (about 15 s the first time)...", flush=True)
    sim = await asyncio.to_thread(Simulator, app.state.seed)
    task = asyncio.create_task(_ticker())
    print(f"Ready: http://{app.state.host}:{app.state.port}", flush=True)
    if app.state.open_browser:
        threading.Timer(0.5, webbrowser.open, args=(f"http://{app.state.host}:{app.state.port}",)).start()
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="TeraSense Live Demo", lifespan=lifespan)
app.state.seed, app.state.host, app.state.port, app.state.open_browser = 0, "127.0.0.1", 8000, True


@app.get("/api/info")
async def api_info():
    return sim.info()


@app.get("/api/state")
async def api_state():
    return {**sim.snapshot(), "history": sim.history_snapshot(), "events": list(sim.events)}


@app.post("/api/set")
async def api_set(body: SetBody):
    vals = {k: v for k, v in body.model_dump(exclude={"node"}).items() if v is not None}
    try:
        sim.set_values(body.node, **vals)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"ok": True, "targets": sim.targets[body.node]}


@app.post("/api/preset")
async def api_preset(body: PresetBody):
    try:
        sim.apply_preset(body.name)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if body.name == "reset":                      # the UI must drop its charts and alert list too
        sim.drain()                               # hello below already carries these; don't send them twice
        await _broadcast({"type": "hello", **_hello()})
    return {"ok": True}


@app.post("/api/speed")
async def api_speed(body: SpeedBody):
    try:
        sim.set_speed(body.speed)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"ok": True, "speed": sim.speed}


def _hello() -> dict:
    return {"info": sim.info(), "snapshot": sim.snapshot(), "history": sim.history_snapshot(),
            "events": list(sim.events)}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    try:
        await ws.send_text(json.dumps({"type": "hello", **_hello()}))
        while True:
            await ws.receive_text()               # the socket is push-only; this just notices a disconnect
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(ws)


@app.get("/")
async def index():
    return FileResponse(FRONTEND / "index.html")


app.mount("/", StaticFiles(directory=FRONTEND), name="frontend")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="TeraSense Live Demo: virtual mine-subsidence simulator")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--seed", type=int, default=0, help="sensor-noise seed; the same seed replays the same demo")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)
    app.state.seed, app.state.host, app.state.port = args.seed, args.host, args.port
    app.state.open_browser = not args.no_browser
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
