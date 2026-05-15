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

ORCHESTRATOR_NAME = "ami-orchestrator"

# Full AMI agent fabric (12 total: orchestrator + 11 specialists)
AGENT_ROSTER = [
    {"name": "ami-orchestrator",           "domain": "routing",       "icon": "🎯", "color": "#fbbf24"},
    {"name": "ami-outage-detection",       "domain": "outage",        "icon": "🚨", "color": "#ef4444"},
    {"name": "ami-theft-detection",        "domain": "theft",         "icon": "🕵️", "color": "#f97316"},
    {"name": "ami-der-management",         "domain": "der",           "icon": "☀️", "color": "#facc15"},
    {"name": "ami-demand-response",        "domain": "dr",            "icon": "⚡", "color": "#a855f7"},
    {"name": "ami-predictive-maintenance", "domain": "maintenance",   "icon": "🔧", "color": "#0ea5e9"},
    {"name": "ami-billing-anomaly",        "domain": "billing",       "icon": "💰", "color": "#10b981"},
    {"name": "ami-customer-service",       "domain": "customer",      "icon": "💬", "color": "#94a3b8"},
    {"name": "ami-grid-cybersecurity",     "domain": "security",      "icon": "🛡️", "color": "#dc2626"},
    {"name": "ami-ev-load-orchestration",  "domain": "ev",            "icon": "🔌", "color": "#22d3ee"},
    {"name": "ami-weather-impact",         "domain": "weather",       "icon": "🌦️", "color": "#60a5fa"},
    {"name": "ami-tariff-optimization",    "domain": "tariff",        "icon": "📊", "color": "#34d399"},
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
        # Routing decision (12-agent fabric)
        if any(w in text_l for w in ["outage", "power out", "no power", "restore"]):
            kind, target = "outage", "ami-outage-detection"
        elif any(w in text_l for w in ["theft", "tamper", "bypass", "suspicious"]):
            kind, target = "theft", "ami-theft-detection"
        elif any(w in text_l for w in ["cyber", "intrusion", "anomalous traffic", "firmware", "spoof"]):
            kind, target = "security", "ami-grid-cybersecurity"
        elif any(w in text_l for w in ["ev ", "ev charger", "charging", "vehicle"]):
            kind, target = "ev", "ami-ev-load-orchestration"
        elif any(w in text_l for w in ["solar", "inverter", "backfeed", "volt-var", "der"]):
            kind, target = "der", "ami-der-management"
        elif any(w in text_l for w in ["demand response", "heat wave", "peak", "load shed", "shed"]):
            kind, target = "dr", "ami-demand-response"
        elif any(w in text_l for w in ["transformer", "harmonic", "maintenance", "aging"]):
            kind, target = "maintenance", "ami-predictive-maintenance"
        elif any(w in text_l for w in ["weather", "storm forecast", "temperature", "humidity"]):
            kind, target = "weather", "ami-weather-impact"
        elif any(w in text_l for w in ["tariff", "rate plan", "tou", "time of use", "pricing"]):
            kind, target = "tariff", "ami-tariff-optimization"
        elif any(w in text_l for w in ["bill", "charge", "amount"]):
            kind, target = "billing", "ami-billing-anomaly"
        else:
            kind, target = "inquiry", "ami-customer-service"

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
        sub_id = self._extract_substation(text) or next(iter(store.substations), "S-01")

        if target == "ami-outage-detection":
            tg = handle_tool_call(store, "group_outage_by_topology", {"substation_id": sub_id})
            yield {"type": "tool_call", "name": "group_outage_by_topology", "arguments": {"substation_id": sub_id}}
            yield {"type": "tool_result", "name": "group_outage_by_topology", "result": tg}
            cc = handle_tool_call(store, "correlate_outage_calls", {"substation_id": sub_id, "time_window_min": 10})
            yield {"type": "tool_result", "name": "correlate_outage_calls", "result": cc}
            offline = tg.get("offline_total", 0)
            if offline == 0:
                handle_tool_call(store, "close_case", {"case_id": case_id, "summary": f"No active outages on {sub_id}.", "recommendation": "n/a"})
                yield {"type": "answer", "text": (
                    f"**No active outages on {sub_id}.**\n"
                    f"All meters reporting; {cc['call_count']} customer calls in the last 10 minutes.\n"
                    f"_(Tip: fire the 'Storm Outage' scenario to inject a feeder fault, then re-ask.)_"
                )}
                return
            pr = handle_tool_call(store, "predict_restoration", {"scope": sub_id, "member_count": offline, "weather_severity": 0.4})
            yield {"type": "tool_result", "name": "predict_restoration", "result": pr}
            cd = handle_tool_call(store, "recommend_crew_dispatch", {"scope": sub_id, "eta_minutes": pr["eta_minutes"]})
            yield {"type": "tool_result", "name": "recommend_crew_dispatch", "result": cd}
            top = (tg.get("transformer_groups") or [{}])[0]
            feeder_groups = tg.get("feeder_groups") or []
            scope_desc = f"feeder **{feeder_groups[0]['feeder_id']}**" if feeder_groups else f"transformer **{top.get('transformer_id','?')}**"
            ans = (
                f"🚨 **Outage on {sub_id}** — {offline} meters offline, concentrated on {scope_desc}.\n"
                f"• {cc['call_count']} customer calls in the last 10m corroborate the topology cluster.\n"
                f"• Predicted restoration: **{pr['eta_minutes']}m** (confidence {int(pr['confidence']*100)}%).\n"
                f"• Recommend dispatching **{cd['crew']}** — on-site ETA ~{cd['on_site_eta_minutes']}m."
            )
            handle_tool_call(store, "close_case", {"case_id": case_id, "summary": f"Outage on {sub_id}: {offline} meters offline.", "recommendation": f"{cd['crew']} → on-site ETA ~{cd['on_site_eta_minutes']}m"})
            yield {"type": "answer", "text": ans}

        elif target == "ami-theft-detection":
            r = handle_tool_call(store, "score_theft", {"scope": {"substation_id": sub_id}})
            yield {"type": "tool_call", "name": "score_theft", "arguments": {"scope": {"substation_id": sub_id}}}
            yield {"type": "tool_result", "name": "score_theft", "result": r}
            suspects = r.get("suspects", [])
            if not suspects:
                ans = f"No theft-pattern meters above threshold on {sub_id} ({r.get('scored', 0)} meters scanned). Try the 'Theft Pattern' scenario to inject candidates."
            else:
                top = suspects[:3]
                lines = "\n".join(f"• `{s['meter_id']}` — score **{s['score']}** · drivers: {', '.join(s['drivers'])} · last {s['last_kw']} kW vs cohort median {s['cohort_median_kw']}" for s in top)
                ans = (
                    f"🕵️ Found **{len(suspects)}** candidate theft cases on {sub_id}.\n"
                    f"Top suspects:\n{lines}\n"
                    f"_Recommendation: field inspection on the top 2; customer outreach for borderline scores._"
                )
            handle_tool_call(store, "close_case", {"case_id": case_id, "summary": f"{len(suspects)} theft candidates on {sub_id}.", "recommendation": "Top 3 → field inspection"})
            yield {"type": "answer", "text": ans}

        elif target == "ami-der-management":
            r1 = handle_tool_call(store, "get_der_status", {"substation_id": sub_id})
            yield {"type": "tool_result", "name": "get_der_status", "result": r1}
            r2 = handle_tool_call(store, "recommend_volt_var", {"substation_id": sub_id, "affected_meters": r1.get("overvoltage_meters", [])})
            yield {"type": "tool_result", "name": "recommend_volt_var", "result": r2}
            curve = r2["proposed_curve"]
            ans = (
                f"☀️ **DER status on {sub_id}**: {r1['der_count']} DER meters · {r1['overvoltage_count']} over-voltage · net export **{r1['net_export_kw']} kW**.\n"
                f"Recommend Volt-VAR curve update per IEEE 1547-2018:\n"
                f"• V1={curve['V1_pu']} pu @ Q={curve['Q1_pct']}%   V2={curve['V2_pu']} pu @ Q={curve['Q2_pct']}%   dead-band ±{curve['V_dead_band_pu']} pu\n"
                f"• Expected secondary-voltage drop: **{r2['expected_voltage_drop_pu']*100:.1f}%**."
            )
            handle_tool_call(store, "close_case", {"case_id": case_id, "summary": f"{r1['overvoltage_count']} DER meters over-voltage on {sub_id}.", "recommendation": json.dumps(curve)})
            yield {"type": "answer", "text": ans}

        elif target == "ami-demand-response":
            r = handle_tool_call(store, "compute_demand_response", {"target_mw": 5, "window_minutes": 60, "cohort_filters": ["residential", "opt_in_DR"]})
            yield {"type": "tool_result", "name": "compute_demand_response", "result": r}
            ans = (
                f"⚡ **DR event staged** ({r['target_mw']} MW target, {r['window_minutes']}m window):\n"
                f"• Cohort: **{r['cohort_size']}** opt-in residential meters\n"
                f"• Projected shed: **{r['projected_shed_mw']} MW** (p10 {r['shed_p10_mw']} · p90 {r['shed_p90_mw']})\n"
                f"• Comfort impact: ~{r['comfort_temperature_rise_f']}°F indoor rise\n"
                f"• Payment liability: **${r['payment_liability_usd']}**\n"
                f"_Awaiting operator approval to dispatch._"
            )
            handle_tool_call(store, "close_case", {"case_id": case_id, "summary": f"DR event staged: {r['cohort_size']} meters → ~{r['projected_shed_mw']} MW.", "recommendation": f"Stage event; ${r['payment_liability_usd']}"})
            yield {"type": "answer", "text": ans}

        elif target == "ami-predictive-maintenance":
            r = handle_tool_call(store, "score_transformer_health", {"substation_id": sub_id})
            yield {"type": "tool_call", "name": "score_transformer_health", "arguments": {"substation_id": sub_id}}
            yield {"type": "tool_result", "name": "score_transformer_health", "result": r}
            worst = r.get("worst", [])
            urgent = [t for t in worst if t["health"] < 30]
            lines = "\n".join(f"• `{t['transformer_id']}` — health **{t['health']}/100** · load {t['load_pct']}% · THD {t['thd_pct']}% · drivers: {', '.join(t['drivers'])} → _{t['recommended_action']}_" for t in worst)
            ans = (
                f"🔧 **Transformer health on {sub_id}** ({r['transformer_count']} units scored):\n"
                f"Bottom 5:\n{lines}\n"
                f"\n**{len(urgent)}** transformer(s) need urgent inspection within 7 days."
            )
            handle_tool_call(store, "close_case", {"case_id": case_id, "summary": f"{len(urgent)} urgent transformers on {sub_id}.", "recommendation": "; ".join(f"{t['transformer_id']}={t['recommended_action']}" for t in worst[:3])})
            yield {"type": "answer", "text": ans}

        elif target == "ami-billing-anomaly":
            sample_meter = next(iter(store.meters))
            r = handle_tool_call(store, "detect_billing_anomaly", {"meter_id": sample_meter, "period_a": "2026-07", "period_b": "2026-08"})
            yield {"type": "tool_result", "name": "detect_billing_anomaly", "result": r}
            pct = round((r["period_b_kwh"] / r["period_a_kwh"] - 1) * 100, 1)
            drivers = "\n".join(f"• {d['name'].replace('_',' ')}: **{d['share_pct']}%** (~${d['dollars']}){'  — '+d['note'] if d.get('note') else ''}" for d in r["drivers"])
            ans = (
                f"📊 **Bill change for `{sample_meter}`**: ${r['delta_dollars']} higher (+{pct}%, {r['period_a_kwh']} → {r['period_b_kwh']} kWh).\n"
                f"Decomposition:\n{drivers}\n"
                f"\n💡 **Recommendation:** {r['recommendation']}"
            )
            handle_tool_call(store, "close_case", {"case_id": case_id, "summary": f"Bill +${r['delta_dollars']} ({pct}%); weather-led.", "recommendation": r["recommendation"]})
            yield {"type": "answer", "text": ans}

        elif target == "ami-grid-cybersecurity":
            # Synthetic but plausible — sample a few meters and pretend we ran an IDS pass
            import random as _r
            sub_meters = store.list_meters_in_substation(sub_id)
            sample = _r.sample(sub_meters, min(8, len(sub_meters))) if sub_meters else []
            findings = []
            for m in sample[:3]:
                findings.append({
                    "meter_id": m["meter_id"],
                    "signal": _r.choice(["unauthorized_firmware_query", "rapid_reauth_burst", "unsigned_command_attempt", "geo_anomalous_traffic"]),
                    "severity": _r.choice(["low", "medium", "high"]),
                    "src_asn": _r.choice(["AS15169", "AS8075", "AS13335"]),
                })
            crit = sum(1 for f in findings if f["severity"] == "high")
            yield {"type": "tool_call", "name": "scan_grid_edge_traffic", "arguments": {"substation_id": sub_id}}
            yield {"type": "tool_result", "name": "scan_grid_edge_traffic", "result": {"ok": True, "findings": findings, "scope": sub_id}}
            handle_tool_call(store, "record_trace", {"case_id": case_id, "agent": target, "step": "scan", "status": "in_progress", "payload": {"findings": findings}})
            lines = "\n".join(f"• `{f['meter_id']}` — **{f['signal']}** · severity {f['severity']} · src {f['src_asn']}" for f in findings) or "• (no anomalies detected in sample)"
            ans = (
                f"🛡️ **Grid-edge cybersecurity scan on {sub_id}** — {len(findings)} signal(s) of interest, {crit} high severity.\n"
                f"{lines}\n"
                f"_Recommendation: {'isolate suspect meters at NIC + open SOC ticket' if crit else 'continue passive monitoring; no action required'}_."
            )
            handle_tool_call(store, "close_case", {"case_id": case_id, "summary": f"{len(findings)} cyber signals on {sub_id}; {crit} high.", "recommendation": "Isolate + SOC ticket" if crit else "Monitor"})
            yield {"type": "answer", "text": ans}

        elif target == "ami-ev-load-orchestration":
            evs = [m for m in store.list_meters_in_substation(sub_id) if m.get("persona") == "ev-owner"]
            current_load_kw = sum((m.get("last_kw") or 0.0) for m in evs)
            shiftable_kw = round(current_load_kw * 0.65, 1)
            yield {"type": "tool_call", "name": "enumerate_ev_chargers", "arguments": {"substation_id": sub_id}}
            yield {"type": "tool_result", "name": "enumerate_ev_chargers", "result": {"ok": True, "ev_count": len(evs), "current_load_kw": round(current_load_kw, 1)}}
            handle_tool_call(store, "record_trace", {"case_id": case_id, "agent": target, "step": "enumerate", "status": "in_progress", "payload": {"ev_count": len(evs)}})
            ans = (
                f"🔌 **EV load on {sub_id}**: {len(evs)} EV-owner meters · current draw **{round(current_load_kw,1)} kW**.\n"
                f"• Shiftable to off-peak window (00:00–05:00): **~{shiftable_kw} kW** ({int(shiftable_kw/max(current_load_kw,0.1)*100)}%)\n"
                f"• Recommend a 2-hour 'pause + resume' nudge on opt-in chargers; expected $ impact for participants: $0.18/kWh saved.\n"
                f"_Avoids ~{round(shiftable_kw*2/1000, 2)} MWh of evening peak._"
            )
            handle_tool_call(store, "close_case", {"case_id": case_id, "summary": f"{len(evs)} EVs on {sub_id}; ~{shiftable_kw} kW shiftable.", "recommendation": "Schedule off-peak nudge"})
            yield {"type": "answer", "text": ans}

        elif target == "ami-weather-impact":
            # Build region label from substation
            region = f"{sub_id}-zone"
            w = handle_tool_call(store, "get_weather", {"region": region, "hours": 24})
            yield {"type": "tool_result", "name": "get_weather", "result": w}
            ss = handle_tool_call(store, "get_substation_status", {"substation_id": sub_id})
            yield {"type": "tool_result", "name": "get_substation_status", "result": ss}
            handle_tool_call(store, "record_trace", {"case_id": case_id, "agent": target, "step": "correlate", "status": "in_progress", "payload": {"cdd": w["cdd"], "load_kw": ss["total_kw"]}})
            # Synthetic correlation
            cooling_share = min(70, int(w["cdd"] * 4))
            ans = (
                f"🌦️ **Weather impact on {sub_id}** (last 24h):\n"
                f"• Heat-index max: **{w['heat_index_max_f']}°F** · CDD: **{w['cdd']}**\n"
                f"• Substation load: **{ss['total_kw']} kW** total across {ss['meter_count']} meters\n"
                f"• Estimated cooling-driven share of load: **~{cooling_share}%**\n"
                f"_Recommendation: pre-cool cohort 30 min before forecast peak (saves ~3% peak demand)._"
            )
            handle_tool_call(store, "close_case", {"case_id": case_id, "summary": f"Weather correlation: ~{cooling_share}% of {sub_id} load is cooling-driven.", "recommendation": "Pre-cool nudge"})
            yield {"type": "answer", "text": ans}

        elif target == "ami-tariff-optimization":
            sample_meter = next(iter(store.meters))
            m = handle_tool_call(store, "get_meter", {"meter_id": sample_meter})["meter"]
            t = handle_tool_call(store, "get_tariff", {"meter_id": sample_meter})
            n = handle_tool_call(store, "compare_to_neighbors", {"meter_id": sample_meter, "days": 30})
            yield {"type": "tool_result", "name": "get_meter", "result": {"meter": m}}
            yield {"type": "tool_result", "name": "get_tariff", "result": t}
            yield {"type": "tool_result", "name": "compare_to_neighbors", "result": n}
            handle_tool_call(store, "record_trace", {"case_id": case_id, "agent": target, "step": "evaluate", "status": "in_progress", "payload": {"current_tariff": t["tariff"]}})
            est_savings = round(n["your_kwh"] * 0.024, 2)
            ans = (
                f"📊 **Tariff optimization for `{m['meter_id']}`** (currently **{t['tariff']}**):\n"
                f"• Last 30 days: **{n['your_kwh']} kWh** (cohort median {n['cohort_median_kwh']} kWh, you're at p{int(n['percentile'])})\n"
                f"• Switching to TOU-D5 with off-peak shifting → estimated savings **~${est_savings}/mo**\n"
                f"• Best fit because: high evening usage, low weekend usage, opt-in eligible."
            )
            handle_tool_call(store, "close_case", {"case_id": case_id, "summary": f"Recommend TOU-D5 for `{m['meter_id']}` (~${est_savings}/mo savings).", "recommendation": "Enroll TOU-D5"})
            yield {"type": "answer", "text": ans}

        else:  # customer-service
            sample_meter = next(iter(store.meters))
            m = handle_tool_call(store, "get_meter", {"meter_id": sample_meter})["meter"]
            ss = handle_tool_call(store, "get_substation_status", {"substation_id": m["substation_id"]})
            yield {"type": "tool_result", "name": "get_meter", "result": {"meter": m}}
            yield {"type": "tool_result", "name": "get_substation_status", "result": ss}
            status = "✅ Power is on" if m.get("online") else "⚠️ Power is currently OUT"
            ans = (
                f"{status} for meter `{m['meter_id']}` ({m['persona']} on tariff {m['tariff']}).\n"
                f"• Last reading: **{m['last_kw']} kW** at **{m['last_voltage']} V**.\n"
                f"• Substation **{m['substation_id']}** is currently serving {ss['meter_count']} meters · "
                f"{ss['offline_count']} offline · {ss['total_kw']} kW total.\n"
                f"_Anything else I can help with?_"
            )
            handle_tool_call(store, "close_case", {"case_id": case_id, "summary": "Customer Q&A answered with grounded meter data.", "recommendation": "n/a"})
            yield {"type": "answer", "text": ans}


runner = FoundryAgentRunner()


# ── Public helper: turn a scenario event into an autonomous agent run ──────

# Maps scenario `kind` → an orchestrator-style chat prompt that triggers the
# right specialist with the right substation context.
EVENT_TO_PROMPT = {
    "outage":             "There is an active outage on substation {substation_id}. Triage and recommend dispatch.",
    "tamper":             "Suspicious tamper readings reported on substation {substation_id}. Hunt for theft.",
    "der_overvoltage":    "Solar backfeed overvoltage detected on substation {substation_id}. Recommend Volt-VAR.",
    "load_forecast_high": "Heat-wave demand forecast triggered. Plan a 5 MW DR event for the next hour.",
    "transformer_health": "Run transformer health on substation {substation_id}.",
    "cyber":              "Cybersecurity anomaly burst on substation {substation_id}. Scan grid edge.",
    "ev_surge":           "EV charging surge on substation {substation_id}. Optimize the load.",
    "weather_alert":      "Weather alert flagged for substation {substation_id}. Correlate impact.",
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
