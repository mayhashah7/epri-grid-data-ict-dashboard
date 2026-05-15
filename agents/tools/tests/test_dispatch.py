"""Smoke tests for ami_tools."""
from datetime import datetime, timezone

from ami_tools.dispatch import handle_tool_call
from ami_tools.schemas import TOOL_SCHEMAS


class _MemCtx:
    def __init__(self):
        self.cases = {}
        self.traces = []
        self.meters = {
            "m1": {"meter_id": "m1", "substation_id": "S-01", "feeder_id": "F-01", "transformer_id": "T-01",
                   "persona": "residential", "tariff": "R-1", "last_kw": 0.4, "last_voltage": 241, "baseline_kw": 0.5},
            "m2": {"meter_id": "m2", "substation_id": "S-01", "feeder_id": "F-01", "transformer_id": "T-01",
                   "persona": "residential", "tariff": "R-1", "last_kw": 0.0, "baseline_kw": 0.7,
                   "flat_overnight": True, "tamper_flag": False, "online": False, "last_voltage": 240},
        }
        self.subs = {"S-01": {"substation_id": "S-01", "name": "Sub 1"}}
        self.transformers = [{"transformer_id": "T-01", "meter_count": 2}]

    def get_meter(self, mid): return self.meters.get(mid)
    def get_meter_reads(self, mid, limit=96): return [{"ts": "now", "kwh": 0.1, "kw": 0.4, "voltage": 240}]
    def list_meters_in_substation(self, sid): return [m for m in self.meters.values() if m["substation_id"] == sid]
    def list_offline_meters(self, sid): return [m for m in self.meters.values() if m["substation_id"] == sid and not m.get("online", True)]
    def list_calls(self, sid, since): return [{"call_id": "c1", "from": "+1...", "ts": datetime.now(timezone.utc).isoformat()}]
    def get_substation(self, sid): return self.subs.get(sid)
    def list_transformers(self, sid): return self.transformers
    def upsert_case(self, doc): self.cases[doc["case_id"]] = doc; return doc
    def get_case(self, cid): return self.cases.get(cid)
    def append_trace(self, doc): self.traces.append(doc); return doc


def test_open_close_case_roundtrip():
    ctx = _MemCtx()
    r = handle_tool_call(ctx, "open_case", {"kind": "outage", "summary": "test"})
    assert r["ok"] and r["case_id"].startswith("case-OUT-")
    cid = r["case_id"]
    r = handle_tool_call(ctx, "record_trace", {"case_id": cid, "agent": "x", "step": "s", "status": "started"})
    assert r["ok"]
    r = handle_tool_call(ctx, "close_case", {"case_id": cid, "summary": "done"})
    assert r["ok"]
    assert ctx.cases[cid]["status"] == "resolved"


def test_outage_topology():
    ctx = _MemCtx()
    ctx.meters["m2"]["online"] = False
    r = handle_tool_call(ctx, "group_outage_by_topology", {"substation_id": "S-01"})
    assert r["ok"]
    assert r["offline_total"] == 1
    assert r["transformer_groups"][0]["transformer_id"] == "T-01"


def test_score_theft_flags_bypass_pattern():
    ctx = _MemCtx()
    ctx.meters["m2"]["last_kw"] = 0.01
    r = handle_tool_call(ctx, "score_theft", {"scope": {"substation_id": "S-01"}})
    assert r["ok"] and len(r["suspects"]) >= 1
    s = r["suspects"][0]
    assert "near_zero_with_history" in s["drivers"] or "flat_overnight" in s["drivers"]


def test_all_schemas_have_handler():
    from ami_tools.dispatch import HANDLERS
    missing = set(TOOL_SCHEMAS) - set(HANDLERS)
    assert not missing, f"missing handlers: {missing}"


def test_unknown_tool():
    ctx = _MemCtx()
    r = handle_tool_call(ctx, "nope", {})
    assert not r["ok"] and "unknown_tool" in r["error"]
