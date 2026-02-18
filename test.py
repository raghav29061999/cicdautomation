from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


@dataclass
class Event:
    event_id: str
    ts_ms: int
    type: str
    session_id: str
    payload: Dict[str, Any]


class InMemoryEventStore:
    """
    Minimal in-memory store.
    Good enough to power dashboard/insights early.
    Replace later with DB/Redis.

    Added:
      - session-scoped KV for orchestration state (e.g., selected_table)
    """

    def __init__(self, max_events: int = 5000) -> None:
        self.max_events = max_events
        self._events: List[Event] = []
        # Session-scoped context, e.g. {"session_id": {"selected_table": "public.orders"}}
        self._session_kv: Dict[str, Dict[str, Any]] = {}

    def add(self, type: str, session_id: Optional[str], payload: Dict[str, Any]) -> Event:
        ev = Event(
            event_id=str(uuid.uuid4()),
            ts_ms=int(time.time() * 1000),
            type=type,
            session_id=session_id or "default",
            payload=payload,
        )
        self._events.append(ev)
        if len(self._events) > self.max_events:
            self._events = self._events[-self.max_events :]
        return ev

    def list(self, limit: int = 200) -> List[Dict[str, Any]]:
        return [asdict(e) for e in self._events[-limit:]]

    def count(self) -> int:
        return len(self._events)

    def counts_by_type(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for e in self._events:
            out[e.type] = out.get(e.type, 0) + 1
        return out

    # ---------------------------
    # NEW: session context helpers
    # ---------------------------

    def set_session_value(self, session_id: str, key: str, value: Any) -> None:
        """
        Store session-scoped orchestration state (in-memory).
        This does NOT change any existing behavior.
        """
        sid = session_id or "default"
        if sid not in self._session_kv:
            self._session_kv[sid] = {}
        self._session_kv[sid][key] = value

        # Optional: store an event for observability/debugging
        self.add(
            type="session_context_set",
            session_id=sid,
            payload={"key": key, "value": value},
        )

    def get_session_value(self, session_id: str, key: str, default: Any = None) -> Any:
        sid = session_id or "default"
        return self._session_kv.get(sid, {}).get(key, default)

    def clear_session(self, session_id: str) -> None:
        sid = session_id or "default"
        if sid in self._session_kv:
            del self._session_kv[sid]
        self.add(type="session_context_cleared", session_id=sid, payload={})
