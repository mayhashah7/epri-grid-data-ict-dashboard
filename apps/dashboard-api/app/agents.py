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

# Grid ICT, Data & Cybersecurity agent fabric (11 total: orchestrator + 10 specialists)
AGENT_ROSTER = [
    {"name": "ict-orchestrator",                "domain": "routing",      "icon": "🧠", "color": "#22d3ee"},
    {"name": "ict-asset-data-verification",     "domain": "verification", "icon": "🧾", "color": "#22d3ee"},
    {"name": "ict-schematic-knowledge-retrieval","domain": "schematics",  "icon": "🔍", "color": "#06b6d4"},
    {"name": "ict-schematic-creation",          "domain": "drafting",     "icon": "✏️", "color": "#0ea5e9"},
    {"name": "ict-gis-adms-sync",               "domain": "sync",         "icon": "🗺️", "color": "#14b8a6"},
    {"name": "ict-digital-twin-validation",     "domain": "twin",         "icon": "🧬", "color": "#0d9488"},
    {"name": "ict-data-exchange-streamlining",  "domain": "exchange",     "icon": "🔁", "color": "#7c3aed"},
    {"name": "ict-knowledge-graph-asset",       "domain": "kg",           "icon": "🕸️", "color": "#a855f7"},
    {"name": "ict-cyber-threat-hunting",        "domain": "threat",       "icon": "🛡️", "color": "#ef4444"},
    {"name": "ict-edge-cyber-anomaly",          "domain": "edge",         "icon": "📡", "color": "#f97316"},
    {"name": "ict-predictive-attack-modeling",  "domain": "attack",       "icon": "🎯", "color": "#dc2626"},
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
        # Routing decision (ICT-specific domains)
        if any(w in text_l for w in ["schematic", "one-line", "drawing", "scheme", "diagram"]):
            if any(w in text_l for w in ["create", "draft", "generate", "new", "design"]):
                kind, target = "drafting", "ict-schematic-creation"
            else:
                kind, target = "schematics", "ict-schematic-knowledge-retrieval"
        elif any(w in text_l for w in ["twin", "digital twin", "model drift", "diverge", "calibrat"]):
            kind, target = "twin", "ict-digital-twin-validation"
        elif any(w in text_l for w in ["crew update", "field update", "conductor", "switching", "gis", "adms", "sync"]):
            kind, target = "sync", "ict-gis-adms-sync"
        elif any(w in text_l for w in ["threat", "lateral", "smb", "apt", "intrusion", "attack path"]):
            if any(w in text_l for w in ["predict", "next step", "kill chain", "path"]):
                kind, target = "attack", "ict-predictive-attack-modeling"
            else:
                kind, target = "threat", "ict-cyber-threat-hunting"
        elif any(w in text_l for w in ["edge", "rtu", "firmware", "meter anomaly", "ied", "unauthorized command"]):
            kind, target = "edge", "ict-edge-cyber-anomaly"
        elif any(w in text_l for w in ["knowledge graph", "kg", "work order", "pivot", "trace"]):
            kind, target = "kg", "ict-knowledge-graph-asset"
        elif any(w in text_l for w in ["nameplate", "ocr", "verify", "asset master", "rating"]):
            kind, target = "verification", "ict-asset-data-verification"
        elif any(w in text_l for w in ["exchange", "cim", "iec 61970", "schema", "mapping"]):
            kind, target = "exchange", "ict-data-exchange-streamlining"
        else:
            kind, target = "schematics", "ict-schematic-knowledge-retrieval"

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
        import random as _r
        sub_id = self._extract_substation(text) or next(iter(store.substations), "S-01")

        if target == "ict-schematic-knowledge-retrieval":
            findings = [
                {"drawing_id": "DWG-138-2019-04", "type": "one-line", "voltage_kv": 138, "year": 2019, "match": "breaker scheme"},
                {"drawing_id": "DWG-138-2021-11", "type": "protection scheme", "voltage_kv": 138, "year": 2021, "match": "overcurrent relay"},
                {"drawing_id": "DWG-138-2023-07", "type": "one-line", "voltage_kv": 138, "year": 2023, "match": "breaker scheme"},
            ]
            yield {"type": "tool_call", "name": "semantic_search_schematics", "arguments": {"query": text[:80]}}
            yield {"type": "tool_result", "name": "semantic_search_schematics", "result": {"hits": findings, "total": 14}}
            lines = "\n".join(f"• `{f['drawing_id']}` — {f['type']} · {f['voltage_kv']}kV · {f['year']}" for f in findings)
            ans = (
                f"🔍 **Schematic search results** (14 total matches, top 3 shown):\n{lines}\n\n"
                f"_Confidence: embeddings match 0.91+. Full results available in the drawing management portal._"
            )
            handle_tool_call(store, "close_case", {"case_id": case_id, "summary": "Schematic search returned 14 matches.", "recommendation": "Review DWG-138-2023-07 first (most recent)"})
            yield {"type": "answer", "text": ans}

        elif target == "ict-schematic-creation":
            draft = {
                "drawing_id": f"DRAFT-{_r.randint(1000,9999)}",
                "type": "one-line",
                "voltage_kv": 25,
                "components": ["2× reclosers", "1× sectionalizer", "4× fuse cutouts", "SCADA RTU"],
                "code_checks": ["NESC 234 ✓", "IEEE C37.60 ✓", "NERC FAC-001 ✓"],
            }
            yield {"type": "tool_call", "name": "generate_schematic", "arguments": {"spec": text[:120]}}
            yield {"type": "tool_result", "name": "generate_schematic", "result": draft}
            comps = ", ".join(draft["components"])
            checks = ", ".join(draft["code_checks"])
            ans = (
                f"✏️ **Draft schematic `{draft['drawing_id']}`** generated for a 25kV recloser zone:\n"
                f"• Components: {comps}\n"
                f"• Code checks passed: {checks}\n"
                f"• Layout optimized for minimal conductor sag and protection coordination.\n"
                f"_Ready for PE review — export to DXF/DWG available._"
            )
            handle_tool_call(store, "close_case", {"case_id": case_id, "summary": f"Draft {draft['drawing_id']} created.", "recommendation": "PE review then issue for construction"})
            yield {"type": "answer", "text": ans}

        elif target == "ict-digital-twin-validation":
            drift_pct = round(_r.uniform(3, 15), 1)
            cause = _r.choice(["unregistered DER", "topology mismatch at feeder F-12", "stale impedance data from 2022 GIS export"])
            yield {"type": "tool_call", "name": "compare_twin_vs_telemetry", "arguments": {"feeder": "F-12", "horizon_h": 1}}
            yield {"type": "tool_result", "name": "compare_twin_vs_telemetry", "result": {"drift_pct": drift_pct, "cause": cause, "calibration_needed": True}}
            ans = (
                f"🧬 **Digital twin drift detected on feeder F-12**: **{drift_pct}% divergence** from live telemetry.\n"
                f"• Root cause: _{cause}_\n"
                f"• Recommended action: re-ingest GIS delta from last crew update + re-run power flow.\n"
                f"• Estimated re-calibration time: ~8 minutes with the automated pipeline."
            )
            handle_tool_call(store, "close_case", {"case_id": case_id, "summary": f"Twin drift {drift_pct}% on F-12: {cause}.", "recommendation": "Re-ingest GIS delta"})
            yield {"type": "answer", "text": ans}

        elif target == "ict-gis-adms-sync":
            yield {"type": "tool_call", "name": "push_field_update_to_adms", "arguments": {"span": "33-7", "change": "conductor reroute"}}
            yield {"type": "tool_result", "name": "push_field_update_to_adms", "result": {"ok": True, "records_updated": 3, "lag_eliminated_min": 47}}
            ans = (
                f"🗺️ **GIS/ADMS sync complete** for span 33-7 conductor reroute:\n"
                f"• 3 topology records updated in ADMS + GIS simultaneously.\n"
                f"• Eliminated **47-minute model lag** that would have persisted until next nightly sync.\n"
                f"• Digital twin automatically re-queued for calibration."
            )
            handle_tool_call(store, "close_case", {"case_id": case_id, "summary": "ADMS/GIS sync: 3 records updated, 47 min lag eliminated.", "recommendation": "Verify in EMS within 5 min"})
            yield {"type": "answer", "text": ans}

        elif target == "ict-cyber-threat-hunting":
            hosts = [f"SUB-{sub_id}-RTU-{_r.randint(1,8)}" for _ in range(3)]
            yield {"type": "tool_call", "name": "hunt_lateral_movement", "arguments": {"protocol": "SMB", "zone": f"{sub_id}"}}
            yield {"type": "tool_result", "name": "hunt_lateral_movement", "result": {"suspicious_hosts": hosts, "technique": "T0886 lateral tool transfer", "confidence": 0.87}}
            lines = "\n".join(f"• `{h}`" for h in hosts)
            ans = (
                f"🛡️ **OT threat hunt on {sub_id}** — MITRE ATT&CK ICS technique **T0886** (lateral tool transfer) detected.\n"
                f"Suspicious hosts ({len(hosts)}):\n{lines}\n"
                f"• Confidence: **87%** · Recommending network isolation + SOC escalation.\n"
                f"_Patch window needed within 24h to prevent persistence._"
            )
            handle_tool_call(store, "close_case", {"case_id": case_id, "summary": f"T0886 on {len(hosts)} hosts in {sub_id}.", "recommendation": "Isolate + SOC P1"})
            yield {"type": "answer", "text": ans}

        elif target == "ict-edge-cyber-anomaly":
            rtu_id = f"RTU-{sub_id}-{_r.randint(100,200)}"
            signal = _r.choice(["unsigned firmware update", "unexpected config read", "unauthenticated command"])
            yield {"type": "tool_call", "name": "analyze_edge_device", "arguments": {"device": rtu_id}}
            yield {"type": "tool_result", "name": "analyze_edge_device", "result": {"device": rtu_id, "signal": signal, "severity": "high", "action": "quarantine"}}
            ans = (
                f"📡 **Edge anomaly on `{rtu_id}`**: _{signal}_ detected.\n"
                f"• Severity: **HIGH** · Automated response: network quarantine applied.\n"
                f"• Firmware hash mismatch vs vendor golden image — likely tamper attempt.\n"
                f"_Recommended: hardware audit + replacement if hash not cleared within 2h._"
            )
            handle_tool_call(store, "close_case", {"case_id": case_id, "summary": f"Edge anomaly on {rtu_id}: {signal}.", "recommendation": "Quarantine + firmware audit"})
            yield {"type": "answer", "text": ans}

        elif target == "ict-predictive-attack-modeling":
            next_steps = ["Establish C2 via Living-off-the-land (T0858)", "Target historian server (T0882)", "Manipulate process setpoints (T0836)"]
            yield {"type": "tool_call", "name": "predict_attack_path", "arguments": {"phase": "recon", "asset": "HMI"}}
            yield {"type": "tool_result", "name": "predict_attack_path", "result": {"current_phase": "recon", "predicted_steps": next_steps, "ttc_hours": 6}}
            steps = "\n".join(f"{i+1}. {s}" for i, s in enumerate(next_steps))
            ans = (
                f"🎯 **Attack path prediction** — adversary in **recon phase** on HMI:\n"
                f"Predicted next steps (within ~6h):\n{steps}\n\n"
                f"• Pre-emptive controls: disable unnecessary HMI remote access, rotate engineering credentials, enable historian audit logging.\n"
                f"_MITRE ATT&CK ICS coverage: T0858, T0882, T0836._"
            )
            handle_tool_call(store, "close_case", {"case_id": case_id, "summary": "Attack path predicted: recon → C2 → historian → setpoint manipulation.", "recommendation": "Pre-emptive credential rotation"})
            yield {"type": "answer", "text": ans}

        elif target == "ict-knowledge-graph-asset":
            related = [
                {"type": "outage", "id": f"OUT-{_r.randint(1000,9999)}", "rel": "caused_by"},
                {"type": "inspection", "id": f"INSP-{_r.randint(100,999)}", "rel": "preceded"},
                {"type": "asset", "id": f"TX-{_r.randint(10,99)}", "rel": "affects"},
            ]
            yield {"type": "tool_call", "name": "kg_pivot", "arguments": {"start": "WO-9821", "depth": 2}}
            yield {"type": "tool_result", "name": "kg_pivot", "result": {"start": "WO-9821", "related": related}}
            lines = "\n".join(f"• [{e['type']}] `{e['id']}` ← _{e['rel']}_" for e in related)
            ans = (
                f"🕸️ **Knowledge graph pivot from WO-9821** (depth-2 traversal):\n{lines}\n\n"
                f"• Cross-linked {len(related)} entities across work-orders, outage, and asset records.\n"
                f"_Use the full graph to trace root cause chains across systems without manual correlation._"
            )
            handle_tool_call(store, "close_case", {"case_id": case_id, "summary": f"KG pivot WO-9821: {len(related)} entities linked.", "recommendation": "Review TX asset for underlying failure"})
            yield {"type": "answer", "text": ans}

        else:  # asset-data-verification / data-exchange / fallback
            yield {"type": "tool_call", "name": "verify_nameplate", "arguments": {"substation_id": sub_id}}
            yield {"type": "tool_result", "name": "verify_nameplate", "result": {"verified": 142, "mismatches": 3, "substation_id": sub_id}}
            ans = (
                f"🧾 **Asset data verification on {sub_id}**: 142 nameplates verified · **3 mismatches** vs asset-master DB.\n"
                f"• Mismatch types: 1× MVA rating, 2× voltage class.\n"
                f"• Recommend field re-inspection on the 3 mismatched records before next planning cycle."
            )
            handle_tool_call(store, "close_case", {"case_id": case_id, "summary": f"3 nameplate mismatches on {sub_id}.", "recommendation": "Field re-inspection"})
            yield {"type": "answer", "text": ans}



runner = FoundryAgentRunner()


# ── Public helper: turn a scenario event into an autonomous agent run ──────

EVENT_TO_PROMPT = {
    "schematic-search":   "Search schematics for 138kV breaker schemes installed since 2018.",
    "twin-drift":         "Digital twin drift detected on feeder F-12 — validate and recommend recalibration.",
    "crew-update":        "Field crew rerouted conductor on span 33-7. Push update to GIS and ADMS.",
    "threat-burst":       "Lateral SMB traffic spike detected between substations {substation_id}. Hunt the threat.",
    "edge-anomaly":       "Edge anomaly on RTU R-118 — unsigned firmware update attempt. Investigate.",
    "attack-prediction":  "Recon phase observed on HMI at substation {substation_id}. Predict attack path.",
    "kg-investigation":   "Pivot from work-order WO-9821 to all related outage and asset events.",
    "schematic-create":   "Draft a new one-line schematic for a 25kV recloser zone.",
}


async def auto_dispatch_for_event(event: dict) -> None:
    """Run the orchestrator + specialist pipeline for a system event."""
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
