"""JSON Schemas for every AMI tool exposed to Foundry agents.

Each schema follows the OpenAI function-calling shape that Foundry's
`FunctionTool` accepts. Keep parameter names stable; agent prompts reference
them.
"""
from __future__ import annotations

from typing import Any

# Convenience helpers ---------------------------------------------------------

def _obj(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


_str = {"type": "string"}
_int = {"type": "integer"}
_num = {"type": "number"}
_bool = {"type": "boolean"}


# Tool schemas ----------------------------------------------------------------

TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    # ── Trace + case lifecycle ──────────────────────────────────────────────
    "record_trace": {
        "name": "record_trace",
        "description": "Append a reasoning step to a case's trace (streamed live to the UI).",
        "parameters": _obj(
            {
                "case_id": _str,
                "agent": _str,
                "step": _str,
                "payload": {"type": "object"},
                "status": {"type": "string", "enum": ["started", "triaging", "dispatched", "in_progress", "info", "resolved", "failed"]},
            },
            ["case_id", "agent", "step", "status"],
        ),
    },
    "open_case": {
        "name": "open_case",
        "description": "Open a new case. Returns the new case_id.",
        "parameters": _obj(
            {
                "kind": {"type": "string", "enum": ["outage", "theft", "der", "dr", "maintenance", "billing", "inquiry"]},
                "summary": _str,
                "scope": {"type": "object", "description": "Optional scope hints (substation_id, meter_id, feeder_id)."},
            },
            ["kind", "summary"],
        ),
    },
    "update_case": {
        "name": "update_case",
        "description": "Update fields (status, summary, recommendation) on an existing case.",
        "parameters": _obj(
            {
                "case_id": _str,
                "fields": {"type": "object"},
            },
            ["case_id", "fields"],
        ),
    },
    "close_case": {
        "name": "close_case",
        "description": "Close a case as resolved with a final summary.",
        "parameters": _obj(
            {"case_id": _str, "summary": _str, "recommendation": _str},
            ["case_id", "summary"],
        ),
    },
    "dispatch_to_agent": {
        "name": "dispatch_to_agent",
        "description": "Hand off a case to a specialist agent.",
        "parameters": _obj(
            {
                "target_agent": {"type": "string", "enum": [
                    "ami-outage-detection", "ami-theft-detection", "ami-der-management",
                    "ami-demand-response", "ami-predictive-maintenance", "ami-billing-anomaly",
                    "ami-customer-service",
                ]},
                "case_id": _str,
                "context": _str,
            },
            ["target_agent", "case_id", "context"],
        ),
    },

    # ── Meter + substation reads ────────────────────────────────────────────
    "get_meter": {
        "name": "get_meter",
        "description": "Fetch a single meter's metadata.",
        "parameters": _obj({"meter_id": _str}, ["meter_id"]),
    },
    "get_meter_reads": {
        "name": "get_meter_reads",
        "description": "Fetch the most recent N interval reads for a meter (default 96 = last 24h).",
        "parameters": _obj(
            {"meter_id": _str, "limit": _int},
            ["meter_id"],
        ),
    },
    "get_substation_status": {
        "name": "get_substation_status",
        "description": "Aggregate live status for a substation (online/offline counts, total kW, voltage band).",
        "parameters": _obj({"substation_id": _str}, ["substation_id"]),
    },

    # ── Outage tools ────────────────────────────────────────────────────────
    "group_outage_by_topology": {
        "name": "group_outage_by_topology",
        "description": "Cluster offline meters by transformer/feeder. Returns groups with member counts.",
        "parameters": _obj(
            {"substation_id": _str, "meter_ids": {"type": "array", "items": _str}},
            ["substation_id"],
        ),
    },
    "correlate_outage_calls": {
        "name": "correlate_outage_calls",
        "description": "Cross-reference inbound IVR/CSR calls with offline meters in a window.",
        "parameters": _obj(
            {"substation_id": _str, "time_window_min": _int},
            ["substation_id"],
        ),
    },
    "predict_restoration": {
        "name": "predict_restoration",
        "description": "Predict restoration ETA for an outage scope (transformer or feeder).",
        "parameters": _obj(
            {"scope": _str, "member_count": _int, "weather_severity": _num},
            ["scope", "member_count"],
        ),
    },
    "recommend_crew_dispatch": {
        "name": "recommend_crew_dispatch",
        "description": "Recommend a crew + ETA for an outage scope.",
        "parameters": _obj({"scope": _str, "eta_minutes": _int}, ["scope"]),
    },

    # ── Theft tools ─────────────────────────────────────────────────────────
    "score_theft": {
        "name": "score_theft",
        "description": "Score every meter in a scope for theft likelihood (0–1) with drivers.",
        "parameters": _obj(
            {"scope": {"type": "object", "description": "{substation_id} or {meter_ids:[]}"}},
            ["scope"],
        ),
    },

    # ── DER tools ───────────────────────────────────────────────────────────
    "get_der_status": {
        "name": "get_der_status",
        "description": "Return DER-equipped meters in a substation with current backfeed + voltage.",
        "parameters": _obj({"substation_id": _str}, ["substation_id"]),
    },
    "recommend_volt_var": {
        "name": "recommend_volt_var",
        "description": "Recommend a Volt-VAR curve adjustment for a substation/affected meters.",
        "parameters": _obj(
            {"substation_id": _str, "affected_meters": {"type": "array", "items": _str}},
            ["substation_id"],
        ),
    },

    # ── Demand response ─────────────────────────────────────────────────────
    "compute_demand_response": {
        "name": "compute_demand_response",
        "description": "Design a DR event: cohort selection + projected MW shed.",
        "parameters": _obj(
            {
                "target_mw": _num,
                "window_minutes": _int,
                "cohort_filters": {"type": "array", "items": _str},
            },
            ["target_mw"],
        ),
    },

    # ── Predictive maintenance ──────────────────────────────────────────────
    "score_transformer_health": {
        "name": "score_transformer_health",
        "description": "Score every transformer in a substation for health (0–100, lower=worse).",
        "parameters": _obj({"substation_id": _str}, ["substation_id"]),
    },

    # ── Billing + customer ──────────────────────────────────────────────────
    "get_weather": {
        "name": "get_weather",
        "description": "Hourly temperature/humidity for a region.",
        "parameters": _obj(
            {"region": _str, "hours": _int},
            ["region"],
        ),
    },
    "get_tariff": {
        "name": "get_tariff",
        "description": "Tariff structure for a meter.",
        "parameters": _obj({"meter_id": _str}, ["meter_id"]),
    },
    "compare_to_neighbors": {
        "name": "compare_to_neighbors",
        "description": "Compare a meter's recent consumption to its peer cohort.",
        "parameters": _obj({"meter_id": _str, "days": _int}, ["meter_id"]),
    },
    "detect_billing_anomaly": {
        "name": "detect_billing_anomaly",
        "description": "Decompose a bill change between two periods into drivers.",
        "parameters": _obj(
            {"meter_id": _str, "period_a": _str, "period_b": _str},
            ["meter_id", "period_a", "period_b"],
        ),
    },
}


def list_tool_names() -> list[str]:
    return sorted(TOOL_SCHEMAS.keys())
