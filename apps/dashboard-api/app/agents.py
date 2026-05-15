"""Foundry agent client — runs the orchestrator agent for chat turns and
handles tool calls back to the local store. Falls back to a deterministic
mock when no Foundry endpoint is configured (so local dev works offline).
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import AsyncIterator

from ami_tools.dispatch import handle_tool_call

from .config import settings
from .store import store

ORCHESTRATOR_NAME = "ict-orchestrator"

# Full AMI agent fabric (12 total: orchestrator + 11 specialists)
AGENT_ROSTER = [
    {"name": "ict-orchestrator", "domain": "routing", "icon": "🧠", "color": "#06b6d4"},
    {"name": "ict-asset-data-verification", "domain": "verification", "icon": "🧾", "color": "#22d3ee"},
    {"name": "ict-schematic-knowledge-retrieval", "domain": "schematics", "icon": "🔍", "color": "#06b6d4"},
    {"name": "ict-schematic-creation", "domain": "drafting", "icon": "✏️", "color": "#0ea5e9"},
    {"name": "ict-gis-adms-sync", "domain": "sync", "icon": "🗺️", "color": "#14b8a6"},
    {"name": "ict-digital-twin-validation", "domain": "twin", "icon": "🧬", "color": "#0d9488"},
    {"name": "ict-data-exchange-streamlining", "domain": "exchange", "icon": "🔁", "color": "#7c3aed"},
    {"name": "ict-knowledge-graph-asset", "domain": "kg", "icon": "🕸️", "color": "#a855f7"},
    {"name": "ict-cyber-threat-hunting", "domain": "threat", "icon": "🛡️", "color": "#ef4444"},
    {"name": "ict-edge-cyber-anomaly", "domain": "edge", "icon": "📡", "color": "#f97316"},
    {"name": "ict-predictive-attack-modeling", "domain": "attack", "icon": "🎯", "color": "#dc2626"},
]


class FoundryAgentRunner:
    """Thin wrapper over the Foundry Agents SDK; lazy imports so the API still
    boots when SDK is unavailable."""

    def __init__(self) -> None:
        self._client = None
        self._agent_ids: dict[str, str] = {}
        self._agent_models: dict[str, str] = {}

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        try:
            from azure.identity import DefaultAzureCredential
            from azure.ai.agents import AgentsClient
        except ImportError:
            print("[agents] SDK not installed — using mock runner")
            return None
        if not settings.foundry_endpoint:
            print("[agents] FOUNDRY_PROJECT_ENDPOINT not set — using mock runner")
            return None
        try:
            cred = DefaultAzureCredential(managed_identity_client_id=settings.azure_client_id or None)
            client = AgentsClient(endpoint=settings.foundry_endpoint, credential=cred)
            for a in client.list_agents():
                self._agent_ids[a.name] = a.id
                self._agent_models[a.name] = getattr(a, "model", "") or ""
            self._client = client
            return self._client
        except Exception as e:  # noqa: BLE001
            print(f"[agents] Foundry client init failed ({e.__class__.__name__}: {e}) — using mock runner")
            return None

    async def chat(self, *, text: str, persona: str | None = None, case_id: str | None = None) -> AsyncIterator[dict]:
        """Run a chat turn through the orchestrator. Yields dict events:
        {type: 'token'|'tool_call'|'tool_result'|'final'|'error', ...}.
        """
        client = self._ensure_client()
        if client is None:
            async for evt in self._mock_chat(text=text, persona=persona, case_id=case_id):
                yield evt
            return

        try:
            agent_id = self._agent_ids.get(ORCHESTRATOR_NAME)
            if not agent_id:
                print(f"[agents] orchestrator agent not in Foundry project — falling back to mock")
                async for evt in self._mock_chat(text=text, persona=persona, case_id=case_id):
                    yield evt
                return

            thread = client.threads.create()
            client.messages.create(
                thread_id=thread.id, role="user",
                content=json.dumps({"kind": "chat", "actor": persona or "operator", "text": text, "case_id": case_id})
            )
            run = client.runs.create(thread_id=thread.id, agent_id=agent_id)

            terminal = {"completed", "failed", "cancelled", "expired", "requires_action"}
            while run.status not in terminal:
                await asyncio.sleep(0.4)
                run = client.runs.get(thread_id=thread.id, run_id=run.id)
                yield {"type": "status", "status": run.status}

                if run.status == "requires_action" and getattr(run, "required_action", None):
                    tool_outputs = []
                    for call in run.required_action.submit_tool_outputs.tool_calls:
                        name = call.function.name
                        args = json.loads(call.function.arguments or "{}")
                        yield {"type": "tool_call", "name": name, "arguments": args}
                        result = handle_tool_call(store, name, args)
                        yield {"type": "tool_result", "name": name, "result": result}
                        tool_outputs.append({"tool_call_id": call.id, "output": json.dumps(result)})
                    run = client.runs.submit_tool_outputs(thread_id=thread.id, run_id=run.id, tool_outputs=tool_outputs)

            if run.status != "completed":
                yield {"type": "error", "message": f"run ended with status {run.status}"}
                return

            messages = client.messages.list(thread_id=thread.id, limit=5)
            assistant = None
            for m in messages:
                if m.role == "assistant":
                    assistant = m
                    break
            if assistant:
                # Concatenate text content blocks
                text_out = "\n".join(
                    getattr(c, "text", {}).get("value", "") if isinstance(getattr(c, "text", None), dict)
                    else (c.text.value if hasattr(c, "text") and hasattr(c.text, "value") else "")
                    for c in (assistant.content or [])
                )
                yield {"type": "final", "text": text_out, "case_id": case_id}
            else:
                yield {"type": "final", "text": "(no assistant message)", "case_id": case_id}
        except Exception as e:  # noqa: BLE001
            print(f"[agents] live runner failed, falling back to mock: {e}")
            async for evt in self._mock_chat(text=text, persona=persona, case_id=case_id):
                yield evt

    # ── Deterministic mock (offline dev) ───────────────────────────────────

    @staticmethod
    def _extract_substation(text: str) -> str | None:
        import re
        m = re.search(r"\b[Ss][-_]?(\d{1,2})\b", text)
        if not m:
            return None
        sid = f"S-{int(m.group(1)):02d}"
        return sid if sid in store.substations else None

    async def _mock_chat(self, *, text: str, persona: str | None, case_id: str | None) -> AsyncIterator[dict]:
        text_l = text.lower()
        # Routing decision (vertical-specific keyword fan-out)
        _routes = [
            (["asset", "data", "verification"], "verification", "ict-asset-data-verification"),
            (["schematic", "knowledge", "retrieval"], "schematics", "ict-schematic-knowledge-retrieval"),
            (["schematic", "creation"], "drafting", "ict-schematic-creation"),
            (["adms", "sync"], "sync", "ict-gis-adms-sync"),
            (["digital", "twin", "validation"], "twin", "ict-digital-twin-validation"),
            (["data", "exchange", "streamlining"], "exchange", "ict-data-exchange-streamlining"),
            (["knowledge", "graph", "asset"], "kg", "ict-knowledge-graph-asset"),
            (["cyber", "threat", "hunting"], "threat", "ict-cyber-threat-hunting"),
            (["edge", "cyber", "anomaly"], "edge", "ict-edge-cyber-anomaly"),
            (["predictive", "attack", "modeling"], "attack", "ict-predictive-attack-modeling"),
        ]
        kind, target = "verification", "ict-asset-data-verification"
        for kws, k, t in _routes:
            if any(w in text_l for w in kws):
                kind, target = k, t
                break

        # Open case (or attach)
        if not case_id:
            r = handle_tool_call(store, "open_case", {"kind": kind, "summary": text[:80]})
            case_id = r["case_id"]
            yield {"type": "tool_call", "name": "open_case", "arguments": {"kind": kind}}
            yield {"type": "tool_result", "name": "open_case", "result": r}

        handle_tool_call(store, "record_trace", {
            "case_id": case_id, "agent": ORCHESTRATOR_NAME, "step": "received",
            "status": "started", "payload": {"text": text, "actor": persona},
        })
        yield {"type": "trace", "step": "received"}

        handle_tool_call(store, "record_trace", {
            "case_id": case_id, "agent": ORCHESTRATOR_NAME, "step": "classify",
            "status": "triaging", "payload": {"target": target, "reason": f"keyword match in '{text[:30]}'"},
        })
        yield {"type": "trace", "step": "classify"}

        handle_tool_call(store, "dispatch_to_agent", {
            "target_agent": target, "case_id": case_id, "context": text[:200],
        })
        yield {"type": "tool_call", "name": "dispatch_to_agent", "arguments": {"target_agent": target}}

        # Specialist runs and returns its substantive answer
        answer = ""
        async for evt in self._mock_specialist(target=target, case_id=case_id, text=text, persona=persona):
            if evt.get("type") == "answer":
                answer = evt["text"]
            else:
                yield evt

        if not answer:
            answer = f"Routed to **{target}** — see case `{case_id}`."
        yield {"type": "final", "text": answer, "case_id": case_id}

    async def _mock_specialist(self, *, target: str, case_id: str, text: str, persona: str | None) -> AsyncIterator[dict]:
        """Generic, vertical-aware specialist runner — grounds the answer in
        live tool calls, then composes a markdown narrative. The deep
        domain-specific reasoning runs on the live Foundry agent (see
        _ensure_client / chat()); this mock is the fallback path."""
        meta = next((a for a in AGENT_ROSTER if a["name"] == target), None)
        domain = (meta or {}).get("domain", "general")
        icon = (meta or {}).get("icon", "🤖")

        events_args = {"limit": 3}
        yield {"type": "tool_call", "name": "list_recent_events", "arguments": events_args}
        events = handle_tool_call(store, "list_recent_events", events_args)
        yield {"type": "tool_result", "name": "list_recent_events", "result": events}

        sub_id = self._extract_substation(text) or next(iter(store.substations), "S-01")
        sub_args = {"substation_id": sub_id}
        yield {"type": "tool_call", "name": "get_substation_status", "arguments": sub_args}
        sub = handle_tool_call(store, "get_substation_status", sub_args)
        yield {"type": "tool_result", "name": "get_substation_status", "result": sub}

        ev_count = len(events.get("events", [])) if isinstance(events, dict) else 0
        sub_load = (sub or {}).get("load_mw", "n/a")
        sub_meters = (sub or {}).get("meter_count", "n/a")

        handle_tool_call(store, "close_case", {
            "case_id": case_id,
            "summary": f"{target} processed request on {sub_id}.",
            "recommendation": f"Forward to {domain} ops review.",
        })

        answer = f"""### {icon} `{target}` analysis

**Findings**
- Scope: **{domain}** (case `{case_id}`)
- Recent events surfaced: **{ev_count}** in the last window — via `list_recent_events`
- Reference site **{sub_id}**: {sub_meters} endpoints, current load **{sub_load} MW** — via `get_substation_status`

**Drivers**
- Two grounded tool calls (see trace) seeded this response.
- The full domain reasoning runs on the live Foundry agent for `{target}` (model pinned per agent spec).

**Recommended Action**
- Open a follow-up work item against `{target}` referencing case `{case_id}`.
- Forward telemetry trace to the {domain} review queue.

**Confidence:** medium — grounded in 2 tool calls; production runs invoke the live Foundry specialist."""
        yield {"type": "answer", "text": answer}

runner = FoundryAgentRunner()


# ── Public helper: turn a scenario event into an autonomous agent run ──────

# Maps scenario `kind` → an orchestrator-style chat prompt that triggers the
# right specialist with the right substation context.
EVENT_TO_PROMPT: dict[str, tuple[str, str]] = {
    "schematic-search": ("Find all 138kV breaker schemes installed since 2018", "ict-schematic-knowledge-retrieval"),
    "twin-drift": ("Live load on feeder F-12 diverges 9% from twin prediction", "ict-digital-twin-validation"),
    "crew-update": ("Crew rerouted conductor on span 33-7 — sync model", "ict-gis-adms-sync"),
    "threat-burst": ("Spike in lateral SMB traffic between substations S-04 ↔ S-09", "ict-cyber-threat-hunting"),
    "edge-anomaly": ("RTU R-118 reporting unsigned firmware update attempt", "ict-edge-cyber-anomaly"),
    "attack-prediction": ("Recon phase observed on HMI — predict next steps", "ict-predictive-attack-modeling"),
    "kg-investigation": ("Pivot from work-order WO-9821 to all related events", "ict-knowledge-graph-asset"),
    "schematic-create": ("Draft a one-line for a new 25kV recloser zone", "ict-schematic-creation"),
}


async def auto_dispatch_for_event(event: dict) -> None:
    """Run the orchestrator + specialist pipeline for a system event.

    Used by `simulator` when a scenario is fired so the user immediately sees
    a case + traces + recommendation populate without typing anything in chat.
    Streams agent activity to the dashboard activity feed via WebSocket.
    """
    kind = event.get("kind")
    sub_id = event.get("substation_id") or next(iter(store.substations), "S-01")
    template = EVENT_TO_PROMPT.get(kind)
    if not template:
        return
    prompt = template.format(substation_id=sub_id)
    try:
        async for evt in runner.chat(text=prompt, persona="system", case_id=None):
            t = evt.get("type")
            if t in ("tool_call", "tool_result", "answer", "final"):
                await store.broadcast({"type": "agent_activity", "data": {
                    "trigger_event_id": event.get("id"),
                    "kind": kind,
                    **evt,
                }})
    except Exception as e:  # noqa: BLE001
        print(f"[agents] auto_dispatch failed for event {kind}: {e}")
