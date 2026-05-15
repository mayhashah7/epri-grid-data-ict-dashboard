"""Tool dispatch — maps tool calls from agent runs to handlers backed by the
running simulator + Cosmos store. The dashboard-api injects a `Context` object
that exposes the data layer; handlers are pure functions over that context.
"""
from __future__ import annotations

import math
import random
import statistics
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Protocol


# ── Context protocol --------------------------------------------------------

class Context(Protocol):
    """The minimum surface a data layer must expose to satisfy ami_tools."""

    def get_meter(self, meter_id: str) -> dict | None: ...
    def get_meter_reads(self, meter_id: str, limit: int = 96) -> list[dict]: ...
    def list_meters_in_substation(self, substation_id: str) -> list[dict]: ...
    def list_offline_meters(self, substation_id: str) -> list[dict]: ...
    def list_calls(self, substation_id: str, since: datetime) -> list[dict]: ...
    def get_substation(self, substation_id: str) -> dict | None: ...
    def list_transformers(self, substation_id: str) -> list[dict]: ...
    def upsert_case(self, doc: dict) -> dict: ...
    def get_case(self, case_id: str) -> dict | None: ...
    def append_trace(self, doc: dict) -> dict: ...


# ── Handlers ----------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ok(**fields) -> dict:
    return {"ok": True, **fields}


def record_trace(ctx: Context, *, case_id: str, agent: str, step: str, status: str, payload: dict | None = None) -> dict:
    doc = {
        "id": str(uuid.uuid4()),
        "case_id": case_id,
        "agent": agent,
        "step": step,
        "status": status,
        "payload": payload or {},
        "ts": _now(),
    }
    ctx.append_trace(doc)
    return _ok(trace_id=doc["id"], ts=doc["ts"])


def open_case(ctx: Context, *, kind: str, summary: str, scope: dict | None = None) -> dict:
    case_id = f"case-{kind[:3].upper()}-{uuid.uuid4().hex[:8]}"
    doc = {
        "id": case_id,
        "case_id": case_id,
        "kind": kind,
        "status": "triaging",
        "summary": summary,
        "scope": scope or {},
        "opened_at": _now(),
        "closed_at": None,
        "owner_agent": "ami-orchestrator",
        "recommendation": None,
    }
    ctx.upsert_case(doc)
    return _ok(case_id=case_id, status="triaging")


def update_case(ctx: Context, *, case_id: str, fields: dict) -> dict:
    case = ctx.get_case(case_id) or {"id": case_id, "case_id": case_id}
    case.update(fields)
    case["updated_at"] = _now()
    ctx.upsert_case(case)
    return _ok(case_id=case_id, fields=list(fields.keys()))


def close_case(ctx: Context, *, case_id: str, summary: str, recommendation: str | None = None) -> dict:
    case = ctx.get_case(case_id) or {"id": case_id, "case_id": case_id}
    case["status"] = "resolved"
    case["summary"] = summary
    if recommendation:
        case["recommendation"] = recommendation
    case["closed_at"] = _now()
    ctx.upsert_case(case)
    return _ok(case_id=case_id, status="resolved")


def dispatch_to_agent(ctx: Context, *, target_agent: str, case_id: str, context: str) -> dict:
    case = ctx.get_case(case_id)
    if case is not None:
        case["routed_to"] = target_agent
        case["status"] = "dispatched"
        case["dispatch_context"] = context
        case["updated_at"] = _now()
        ctx.upsert_case(case)
    return _ok(target_agent=target_agent, case_id=case_id)


def get_meter(ctx: Context, *, meter_id: str) -> dict:
    m = ctx.get_meter(meter_id)
    return _ok(meter=m) if m else {"ok": False, "error": "meter_not_found"}


def get_meter_reads(ctx: Context, *, meter_id: str, limit: int = 96) -> dict:
    reads = ctx.get_meter_reads(meter_id, limit=limit)
    return _ok(meter_id=meter_id, count=len(reads), reads=reads)


def get_substation_status(ctx: Context, *, substation_id: str) -> dict:
    sub = ctx.get_substation(substation_id)
    if not sub:
        return {"ok": False, "error": "substation_not_found"}
    meters = ctx.list_meters_in_substation(substation_id)
    offline = ctx.list_offline_meters(substation_id)
    total_kw = sum((m.get("last_kw") or 0.0) for m in meters)
    voltages = [m.get("last_voltage") for m in meters if m.get("last_voltage")]
    return _ok(
        substation_id=substation_id,
        meter_count=len(meters),
        offline_count=len(offline),
        total_kw=round(total_kw, 1),
        voltage_min=round(min(voltages), 1) if voltages else None,
        voltage_max=round(max(voltages), 1) if voltages else None,
        voltage_mean=round(statistics.mean(voltages), 1) if voltages else None,
    )


def group_outage_by_topology(ctx: Context, *, substation_id: str, meter_ids: list[str] | None = None) -> dict:
    offline = ctx.list_offline_meters(substation_id)
    if meter_ids:
        wanted = set(meter_ids)
        offline = [m for m in offline if m["meter_id"] in wanted]
    by_xfmr: dict[str, list[str]] = {}
    by_feeder: dict[str, list[str]] = {}
    for m in offline:
        by_xfmr.setdefault(m["transformer_id"], []).append(m["meter_id"])
        by_feeder.setdefault(m["feeder_id"], []).append(m["meter_id"])
    transformers = ctx.list_transformers(substation_id)
    xfmr_size = {t["transformer_id"]: t["meter_count"] for t in transformers}
    groups = []
    for xid, members in by_xfmr.items():
        total = xfmr_size.get(xid, len(members))
        groups.append({
            "transformer_id": xid,
            "offline": len(members),
            "of_total": total,
            "fraction": round(len(members) / max(total, 1), 2),
        })
    groups.sort(key=lambda g: -g["fraction"])
    return _ok(
        substation_id=substation_id,
        offline_total=len(offline),
        transformer_groups=groups[:10],
        feeder_groups=[{"feeder_id": f, "offline": len(v)} for f, v in by_feeder.items()],
    )


def correlate_outage_calls(ctx: Context, *, substation_id: str, time_window_min: int = 10) -> dict:
    since = datetime.now(timezone.utc) - timedelta(minutes=time_window_min)
    calls = ctx.list_calls(substation_id, since=since)
    return _ok(
        substation_id=substation_id,
        window_minutes=time_window_min,
        call_count=len(calls),
        calls=calls[:25],
    )


def predict_restoration(ctx: Context, *, scope: str, member_count: int, weather_severity: float = 0.0) -> dict:
    base = 30 + math.sqrt(max(member_count, 1)) * 4
    base += weather_severity * 25
    eta = int(min(max(base, 20), 240))
    confidence = round(max(0.5, 1.0 - weather_severity * 0.3 - (1.0 / max(member_count, 1))), 2)
    return _ok(scope=scope, eta_minutes=eta, confidence=confidence)


_CREWS = ["Crew Alpha", "Crew Bravo", "Crew Charlie", "Crew Delta"]


def recommend_crew_dispatch(ctx: Context, *, scope: str, eta_minutes: int | None = None) -> dict:
    crew = random.choice(_CREWS)
    travel = random.randint(8, 22)
    return _ok(
        crew=crew,
        scope=scope,
        travel_minutes=travel,
        on_site_eta_minutes=(eta_minutes or 0) + travel,
        confidence=0.88,
    )


# ── Theft scoring -----------------------------------------------------------

def score_theft(ctx: Context, *, scope: dict) -> dict:
    sub_id = scope.get("substation_id")
    meter_ids = scope.get("meter_ids") or []
    if sub_id:
        meters = ctx.list_meters_in_substation(sub_id)
    else:
        meters = [m for m in (ctx.get_meter(mid) for mid in meter_ids) if m]

    if not meters:
        return {"ok": False, "error": "no_meters_in_scope"}

    cohort_kw = [m.get("last_kw") or 0.0 for m in meters if (m.get("persona") or "").startswith("residential")]
    cohort_median = statistics.median(cohort_kw) if cohort_kw else 1.0

    suspects = []
    for m in meters:
        drivers = []
        score = 0.0
        kw = m.get("last_kw") or 0.0
        if m.get("tamper_flag"):
            drivers.append("tamper_flag")
            score += 0.5
        if 0 < kw < 0.05 and (m.get("baseline_kw") or 0) > 0.4:
            drivers.append("near_zero_with_history")
            score += 0.35
        if m.get("flat_overnight"):
            drivers.append("flat_overnight")
            score += 0.25
        if cohort_median > 0 and kw < cohort_median * 0.15:
            drivers.append("cohort_zscore_low")
            score += 0.15
        score = min(round(score, 2), 1.0)
        if score >= 0.4:
            suspects.append({
                "meter_id": m["meter_id"],
                "score": score,
                "drivers": drivers,
                "last_kw": round(kw, 3),
                "cohort_median_kw": round(cohort_median, 3),
            })

    suspects.sort(key=lambda s: -s["score"])
    return _ok(scope=scope, scored=len(meters), suspects=suspects[:10])


# ── DER ---------------------------------------------------------------------

def get_der_status(ctx: Context, *, substation_id: str) -> dict:
    meters = [m for m in ctx.list_meters_in_substation(substation_id) if m.get("persona") in {"solar", "ev-owner"}]
    over = [m for m in meters if (m.get("last_voltage") or 240) > 252]  # > 1.05 pu of 240V
    backfeed = sum(min((m.get("last_kw") or 0.0), 0.0) for m in meters)
    return _ok(
        substation_id=substation_id,
        der_count=len(meters),
        overvoltage_count=len(over),
        net_export_kw=round(-backfeed, 1),
        overvoltage_meters=[m["meter_id"] for m in over[:25]],
    )


def recommend_volt_var(ctx: Context, *, substation_id: str, affected_meters: list[str] | None = None) -> dict:
    proposed = {
        "V1_pu": 0.97, "Q1_pct": +30,
        "V2_pu": 1.03, "Q2_pct": -30,
        "V_dead_band_pu": 0.005,
    }
    return _ok(
        substation_id=substation_id,
        affected_count=len(affected_meters or []),
        proposed_curve=proposed,
        expected_voltage_drop_pu=0.012,
        standard_reference="IEEE 1547-2018 §5.3.3",
    )


# ── Demand response ---------------------------------------------------------

def compute_demand_response(ctx: Context, *, target_mw: float, window_minutes: int = 60, cohort_filters: list[str] | None = None) -> dict:
    cohort_filters = cohort_filters or ["residential", "opt_in_DR"]
    # Synthetic: assume 15 kWh/event/meter resi, 2 kW shed avg
    avg_shed_kw = 2.0
    needed = math.ceil(target_mw * 1000 / avg_shed_kw)
    cohort_size = int(needed * 1.15)  # 15% margin
    payment_per_meter = 1.50 * (window_minutes / 60)
    return _ok(
        target_mw=target_mw,
        window_minutes=window_minutes,
        cohort_filters=cohort_filters,
        cohort_size=cohort_size,
        projected_shed_mw=round(cohort_size * avg_shed_kw / 1000 * 0.95, 2),
        shed_p10_mw=round(cohort_size * avg_shed_kw / 1000 * 0.78, 2),
        shed_p90_mw=round(cohort_size * avg_shed_kw / 1000 * 1.08, 2),
        payment_liability_usd=round(cohort_size * payment_per_meter, 2),
        comfort_temperature_rise_f=2.5,
    )


# ── Predictive maintenance --------------------------------------------------

def score_transformer_health(ctx: Context, *, substation_id: str) -> dict:
    transformers = ctx.list_transformers(substation_id)
    rng = random.Random(hash(substation_id) & 0xffffffff)
    scored = []
    for t in transformers:
        health = max(5, min(100, int(rng.gauss(72, 18))))
        thd = round(rng.uniform(2.0, 9.0), 1)
        load_pct = round(rng.uniform(45, 115), 1)
        drivers = []
        if load_pct > 100: drivers.append(f"sustained_load_{load_pct}%")
        if thd > 6: drivers.append(f"high_thd_{thd}%")
        if health < 50: drivers.append("declining_health_trend")
        action = "monitor"
        if health < 30: action = "urgent_inspection_7d"
        elif health < 60: action = "schedule_inspection_30d"
        scored.append({
            "transformer_id": t["transformer_id"],
            "health": health,
            "load_pct": load_pct,
            "thd_pct": thd,
            "drivers": drivers or ["nominal"],
            "recommended_action": action,
        })
    scored.sort(key=lambda s: s["health"])
    return _ok(substation_id=substation_id, transformer_count=len(scored), worst=scored[:5], all=scored)


# ── Billing + weather + neighbors -------------------------------------------

def get_weather(ctx: Context, *, region: str, hours: int = 24) -> dict:
    rng = random.Random(hash((region, hours)) & 0xffffffff)
    base = 88 + rng.uniform(-4, 4)  # F
    series = [round(base + 10 * math.sin(i / 4) + rng.uniform(-2, 2), 1) for i in range(hours)]
    cdd = sum(max(t - 65, 0) for t in series) / 24
    return _ok(region=region, hours=hours, temp_f=series, cdd=round(cdd, 1), heat_index_max_f=max(series))


def get_tariff(ctx: Context, *, meter_id: str) -> dict:
    m = ctx.get_meter(meter_id)
    if not m:
        return {"ok": False, "error": "meter_not_found"}
    return _ok(meter_id=meter_id, tariff=m.get("tariff", "R-1"), tou_eligible=True, tiers=[
        {"name": "Tier 1", "kwh_band": "0-500", "rate": 0.13},
        {"name": "Tier 2", "kwh_band": "501-1000", "rate": 0.17},
        {"name": "Tier 3", "kwh_band": "1001+", "rate": 0.24},
    ])


def compare_to_neighbors(ctx: Context, *, meter_id: str, days: int = 30) -> dict:
    m = ctx.get_meter(meter_id)
    if not m:
        return {"ok": False, "error": "meter_not_found"}
    cohort = [x for x in ctx.list_meters_in_substation(m["substation_id"])
              if x.get("persona") == m.get("persona")]
    cohort_kwh = [(c.get("baseline_kw") or 0.5) * 24 * days for c in cohort]
    median_kwh = statistics.median(cohort_kwh) if cohort_kwh else 0
    you = (m.get("baseline_kw") or 0.5) * 24 * days * (1 + random.uniform(-0.1, 0.4))
    return _ok(
        meter_id=meter_id,
        days=days,
        your_kwh=round(you, 1),
        cohort_median_kwh=round(median_kwh, 1),
        percentile=round(min(99, max(1, 50 + (you - median_kwh) / max(median_kwh, 1) * 50)), 0),
        cohort_size=len(cohort),
    )


def detect_billing_anomaly(ctx: Context, *, meter_id: str, period_a: str, period_b: str) -> dict:
    m = ctx.get_meter(meter_id)
    if not m:
        return {"ok": False, "error": "meter_not_found"}
    rng = random.Random(hash((meter_id, period_a, period_b)) & 0xffffffff)
    base_kwh = (m.get("baseline_kw") or 0.5) * 24 * 30
    a_kwh = base_kwh * (1 + rng.uniform(-0.05, 0.05))
    b_kwh = a_kwh * (1 + rng.uniform(0.20, 0.45))
    delta_kwh = b_kwh - a_kwh
    delta_dollars = round(delta_kwh * 0.18, 2)
    drivers = [
        {"name": "weather_cdd_hdd",    "share_pct": 55, "dollars": round(delta_dollars * 0.55, 2)},
        {"name": "new_persistent_load","share_pct": 25, "dollars": round(delta_dollars * 0.25, 2), "note": "Suspected EV charger added on day 12"},
        {"name": "tariff_step",        "share_pct": 12, "dollars": round(delta_dollars * 0.12, 2)},
        {"name": "peak_hour_shift",    "share_pct": 8,  "dollars": round(delta_dollars * 0.08, 2)},
    ]
    return _ok(
        meter_id=meter_id,
        period_a=period_a,
        period_b=period_b,
        period_a_kwh=round(a_kwh, 1),
        period_b_kwh=round(b_kwh, 1),
        delta_kwh=round(delta_kwh, 1),
        delta_dollars=delta_dollars,
        drivers=drivers,
        recommendation="Enroll in TOU-D5 — projected savings ~$22/mo",
    )


# ── Dispatch table ----------------------------------------------------------

HANDLERS: dict[str, Callable[..., dict]] = {
    "record_trace": record_trace,
    "open_case": open_case,
    "update_case": update_case,
    "close_case": close_case,
    "dispatch_to_agent": dispatch_to_agent,
    "get_meter": get_meter,
    "get_meter_reads": get_meter_reads,
    "get_substation_status": get_substation_status,
    "group_outage_by_topology": group_outage_by_topology,
    "correlate_outage_calls": correlate_outage_calls,
    "predict_restoration": predict_restoration,
    "recommend_crew_dispatch": recommend_crew_dispatch,
    "score_theft": score_theft,
    "get_der_status": get_der_status,
    "recommend_volt_var": recommend_volt_var,
    "compute_demand_response": compute_demand_response,
    "score_transformer_health": score_transformer_health,
    "get_weather": get_weather,
    "get_tariff": get_tariff,
    "compare_to_neighbors": compare_to_neighbors,
    "detect_billing_anomaly": detect_billing_anomaly,
}


def handle_tool_call(ctx: Context, name: str, arguments: dict[str, Any]) -> dict:
    """Run a tool by name with kwargs; returns the JSON-able result dict."""
    fn = HANDLERS.get(name)
    if fn is None:
        return {"ok": False, "error": f"unknown_tool:{name}"}
    try:
        return fn(ctx, **arguments)
    except TypeError as e:
        return {"ok": False, "error": f"bad_arguments:{e}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"tool_failed:{e.__class__.__name__}:{e}"}
