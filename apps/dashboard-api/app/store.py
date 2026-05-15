"""In-memory data store + optional Cosmos passthrough.

The store satisfies the `ami_tools.dispatch.Context` Protocol so tool handlers
work identically locally and in production.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Iterable

from .config import settings


class Store:
    def __init__(self) -> None:
        self.meters: dict[str, dict] = {}
        self.substations: dict[str, dict] = {}
        self.transformers_by_sub: dict[str, list[dict]] = {}
        self.reads_by_meter: dict[str, deque] = defaultdict(lambda: deque(maxlen=192))
        self.events: deque = deque(maxlen=2000)
        self.calls: list[dict] = []
        self.cases: dict[str, dict] = {}
        self.traces_by_case: dict[str, list[dict]] = defaultdict(list)
        self._lock = asyncio.Lock()
        # WebSocket fan-out
        self._subscribers: set[asyncio.Queue] = set()
        self._cosmos = None  # set later if Cosmos available
        self._fault_overrides: dict[str, dict] = {}

    # ── Subscription / broadcast ───────────────────────────────────────────

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=512)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    async def broadcast(self, msg: dict) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass

    # ── Cosmos hookup (best-effort) ────────────────────────────────────────

    async def attach_cosmos(self) -> None:
        if not settings.cosmos_endpoint:
            return
        try:
            from azure.cosmos.aio import CosmosClient  # type: ignore
            from azure.identity.aio import DefaultAzureCredential  # type: ignore

            cred = DefaultAzureCredential()
            client = CosmosClient(settings.cosmos_endpoint, credential=cred)
            db = client.get_database_client(settings.cosmos_database)
            self._cosmos = {
                "client": client,
                "credential": cred,
                "cases": db.get_container_client("cases"),
                "traces": db.get_container_client("traces"),
                "events": db.get_container_client("events"),
            }
        except Exception as e:  # noqa: BLE001
            print(f"[store] Cosmos attach failed (continuing in-memory): {e}")

    async def shutdown(self) -> None:
        if self._cosmos:
            await self._cosmos["client"].close()
            await self._cosmos["credential"].close()

    # ── Context Protocol (sync, used by tool handlers) ─────────────────────

    def get_meter(self, meter_id: str) -> dict | None:
        return self.meters.get(meter_id)

    def get_meter_reads(self, meter_id: str, limit: int = 96) -> list[dict]:
        return list(self.reads_by_meter.get(meter_id, []))[-limit:]

    def list_meters_in_substation(self, substation_id: str) -> list[dict]:
        return [m for m in self.meters.values() if m["substation_id"] == substation_id]

    def list_offline_meters(self, substation_id: str) -> list[dict]:
        return [m for m in self.meters.values()
                if m["substation_id"] == substation_id and not m.get("online", True)]

    def list_calls(self, substation_id: str, since: datetime) -> list[dict]:
        return [{k: v for k, v in c.items() if k != "ts_dt"} for c in self.calls
                if c["substation_id"] == substation_id and c["ts_dt"] >= since]

    def get_substation(self, substation_id: str) -> dict | None:
        return self.substations.get(substation_id)

    def list_transformers(self, substation_id: str) -> list[dict]:
        return self.transformers_by_sub.get(substation_id, [])

    def upsert_case(self, doc: dict) -> dict:
        self.cases[doc["case_id"]] = doc
        # Best-effort persist
        self._fire_and_forget(self._persist_case(doc))
        # Broadcast
        self._fire_and_forget(self.broadcast({"type": "case", "data": doc}))
        return doc

    def get_case(self, case_id: str) -> dict | None:
        return self.cases.get(case_id)

    def append_trace(self, doc: dict) -> dict:
        self.traces_by_case[doc["case_id"]].append(doc)
        self._fire_and_forget(self._persist_trace(doc))
        self._fire_and_forget(self.broadcast({"type": "trace", "data": doc}))
        return doc

    # ── Cosmos persistence (async, fire-and-forget) ────────────────────────

    async def _persist_case(self, doc: dict) -> None:
        if not self._cosmos:
            return
        try:
            await self._cosmos["cases"].upsert_item(doc)
        except Exception as e:  # noqa: BLE001
            print(f"[store] case persist failed: {e}")

    async def _persist_trace(self, doc: dict) -> None:
        if not self._cosmos:
            return
        try:
            await self._cosmos["traces"].upsert_item(doc)
        except Exception as e:  # noqa: BLE001
            print(f"[store] trace persist failed: {e}")

    async def _persist_event(self, doc: dict) -> None:
        if not self._cosmos:
            return
        try:
            await self._cosmos["events"].upsert_item(doc)
        except Exception as e:  # noqa: BLE001
            print(f"[store] event persist failed: {e}")

    @staticmethod
    def _fire_and_forget(coro) -> None:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(coro)
            else:
                coro.close()
        except RuntimeError:
            coro.close()

    # ── Event/calls helpers ────────────────────────────────────────────────

    def add_event(self, evt: dict) -> None:
        self.events.append(evt)
        self._fire_and_forget(self._persist_event(evt))
        self._fire_and_forget(self.broadcast({"type": "event", "data": evt}))

    def add_call(self, call: dict) -> None:
        call["ts_dt"] = datetime.fromisoformat(call["ts"])
        self.calls.append(call)


store = Store()
