"""FastAPI app — REST + WebSocket + chat endpoint."""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .agents import runner
from .config import settings
from .simulator import SCENARIOS, build_topology, simulator_loop
from .store import store


async def _auto_seed_agents() -> None:
    """Wait 30 s then attempt to seed all agents into Foundry via subprocess."""
    import subprocess
    import os as _os
    if not settings.foundry_endpoint:
        return
    await asyncio.sleep(30)
    seed_script = "/app/scripts/seed-foundry-agents.py"
    if not _os.path.exists(seed_script):
        print("[startup] seed script not found — skipping auto-seed")
        return
    print("[startup] Auto-seeding Foundry agents...")
    env = {**_os.environ,
           "FOUNDRY_PROJECT_ENDPOINT": settings.foundry_endpoint,
           "AOAI_DEPLOYMENT_NAME": settings.aoai_deployment or "gpt-4o"}
    try:
        import sys as _sys
        result = subprocess.run(
            [_sys.executable, seed_script, "--agents-dir", "/app/agents"],
            capture_output=True, text=True, timeout=120, env=env,
        )
        if result.stdout:
            print(result.stdout[-2000:])
        if result.returncode != 0:
            print(f"[startup] seed non-zero exit: {result.stderr[-500:]}")
        else:
            print("[startup] Foundry agent seed complete ✓")
    except Exception as e:  # noqa: BLE001
        print(f"[startup] seed failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    build_topology(seed=settings.seed)
    await store.attach_cosmos()
    task: asyncio.Task | None = None
    if settings.enable_simulator:
        task = asyncio.create_task(simulator_loop())
        asyncio.create_task(_auto_seed_agents())
    yield
    if task:
        task.cancel()
    await store.shutdown()


app = FastAPI(title="AMI Agentic Dashboard API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── REST ──────────────────────────────────────────────────────────────────


@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "meter_count": len(store.meters),
        "substation_count": len(store.substations),
        "foundry_configured": bool(settings.foundry_endpoint),
        "cosmos_configured": bool(settings.cosmos_endpoint),
    }


@app.get("/api/substations")
async def list_substations() -> list[dict]:
    out = []
    for sid, sub in store.substations.items():
        meters = store.list_meters_in_substation(sid)
        offline = [m for m in meters if not m["online"]]
        out.append({
            **sub,
            "meter_count": len(meters),
            "offline_count": len(offline),
            "total_kw": round(sum(m.get("last_kw", 0) for m in meters), 1),
        })
    return out


@app.get("/api/meters")
async def list_meters(substation_id: str | None = None, limit: int = 500) -> list[dict]:
    meters = store.meters.values()
    if substation_id:
        meters = [m for m in meters if m["substation_id"] == substation_id]
    out = []
    for m in list(meters)[:limit]:
        out.append({k: m.get(k) for k in (
            "meter_id", "substation_id", "feeder_id", "transformer_id",
            "persona", "tariff", "lat", "lon", "online", "last_kw", "last_voltage",
        )})
    return out


@app.get("/api/meters/{meter_id}")
async def get_meter(meter_id: str) -> dict:
    m = store.get_meter(meter_id)
    if not m:
        raise HTTPException(404, "meter not found")
    return {**m, "reads": store.get_meter_reads(meter_id, limit=96)}


@app.get("/api/events")
async def list_events(limit: int = 50) -> list[dict]:
    return list(store.events)[-limit:][::-1]


@app.get("/api/cases")
async def list_cases(limit: int = 50) -> list[dict]:
    return sorted(store.cases.values(), key=lambda c: c.get("opened_at", ""), reverse=True)[:limit]


@app.get("/api/cases/{case_id}")
async def get_case(case_id: str) -> dict:
    c = store.get_case(case_id)
    if not c:
        raise HTTPException(404, "case not found")
    return {**c, "traces": store.traces_by_case.get(case_id, [])}


@app.get("/api/agents/roster")
async def agent_roster() -> list[dict]:
    """Return the full agent fabric definition for UI rendering, augmented
    with the live Foundry agent id + model when available."""
    from .agents import AGENT_ROSTER, runner
    runner._ensure_client()  # populate id/model maps if not yet
    out = []
    for a in AGENT_ROSTER:
        item = dict(a)
        item["agent_id"] = runner._agent_ids.get(a["name"])
        item["model"] = runner._agent_models.get(a["name"])
        item["registered"] = item["agent_id"] is not None
        out.append(item)
    return out


@app.get("/api/agents/traces")
async def list_traces(case_id: str) -> list[dict]:
    return store.traces_by_case.get(case_id, [])


# ── Scenarios ─────────────────────────────────────────────────────────────


class ScenarioReq(BaseModel):
    substation_id: str | None = None
    feeder_index: int | None = None
    count: int | None = None


@app.post("/api/scenarios/{name}")
async def run_scenario(name: str, req: ScenarioReq | None = None) -> dict:
    fn = SCENARIOS.get(name)
    if not fn:
        raise HTTPException(404, f"unknown scenario {name}; choices: {list(SCENARIOS)}")
    kwargs = {k: v for k, v in (req.dict() if req else {}).items() if v is not None}
    return await fn(**kwargs)


# ── Chat ──────────────────────────────────────────────────────────────────


class ChatReq(BaseModel):
    text: str
    persona: str | None = "operator"
    case_id: str | None = None


@app.post("/api/chat")
async def chat(req: ChatReq):
    """Streams JSON Lines (one event per line) from the orchestrator."""
    from fastapi.responses import StreamingResponse

    async def gen():
        async for evt in runner.chat(text=req.text, persona=req.persona, case_id=req.case_id):
            yield (json.dumps(evt) + "\n").encode()

    return StreamingResponse(gen(), media_type="application/x-ndjson")


# ── WebSocket fan-out ─────────────────────────────────────────────────────


@app.websocket("/ws/stream")
async def ws_stream(ws: WebSocket):
    await ws.accept()
    q = store.subscribe()
    try:
        # Initial snapshot
        await ws.send_json({"type": "snapshot", "data": {
            "substations": [{**s, "meter_count": len(store.list_meters_in_substation(s["substation_id"]))}
                            for s in store.substations.values()],
            "events": list(store.events)[-25:],
            "cases": sorted(store.cases.values(), key=lambda c: c.get("opened_at", ""), reverse=True)[:10],
        }})
        while True:
            msg = await q.get()
            await ws.send_json(msg)
    except WebSocketDisconnect:
        pass
    finally:
        store.unsubscribe(q)
