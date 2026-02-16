Below is a **simple, minimal** API layer you can drop into your backend. It adds:

* `POST /api/chat`
* `GET /api/dashboard/summary`
* `GET /api/insights/overview`
* A **basic in-memory “event log”** (not a full logging system, but enough for dashboard/insights)
* Python `logging` setup + a request logging middleware

I’ll show:

1. **Directory structure**
2. **Code per module** (copy-paste friendly)

---

## 1) Directory structure (minimal)

Assuming your current layout is like:

```
agno_agent/backend/
  main.py
  src/
    agents/
      agent_1.py
      agent_2.py
      agent_3.py
    tools/
    config/
```

Add these:

```
agno_agent/backend/
  main.py                      # you can rename your current main.py to temp_main.py
  src/
    api/
      __init__.py
      app_factory.py
      logging_setup.py
      store.py
      models.py
      routes/
        __init__.py
        chat.py
        dashboard.py
        insights.py
```

Optional but recommended (to make agent imports clean):

```
agno_agent/backend/src/agents/
  __init__.py
```

---

## 2) Code per module

### FILE: `src/api/logging_setup.py`

```python
import logging
import os
from logging.handlers import RotatingFileHandler


def configure_logging() -> None:
    """
    Simple logging:
    - Console always
    - Optional rotating file if LOG_FILE is set
    """
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    root = logging.getLogger()
    root.setLevel(log_level)

    # Avoid duplicate handlers if reload=True
    if root.handlers:
        return

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    log_file = os.getenv("LOG_FILE")
    if log_file:
        file_handler = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=3)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
```

---

### FILE: `src/api/store.py`

```python
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
    """

    def __init__(self, max_events: int = 5000) -> None:
        self.max_events = max_events
        self._events: List[Event] = []

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
```

---

### FILE: `src/api/models.py`

```python
from __future__ import annotations

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: Optional[str] = None
    agent: Optional[str] = Field(default="agent_1", description="agent_1 | agent_2 | agent_3")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    session_id: str
    agent: str
    reply: str
    raw: Dict[str, Any] = Field(default_factory=dict)


class DashboardSummary(BaseModel):
    status: str
    agents: Dict[str, str]
    total_events: int
    events_by_type: Dict[str, int]


class InsightsOverview(BaseModel):
    total_events: int
    events_by_type: Dict[str, int]
    recent_events: list
```

---

### FILE: `src/api/routes/chat.py`

```python
from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from src.api.models import ChatRequest, ChatResponse
from src.api.store import InMemoryEventStore

log = logging.getLogger("api.chat")
router = APIRouter(prefix="/api", tags=["chat"])


# --- Dependency hooks (set in app_factory) ---
def get_agents() -> Dict[str, Any]:
    raise RuntimeError("Agents dependency not wired")


def get_store() -> InMemoryEventStore:
    raise RuntimeError("Store dependency not wired")


def _call_agent(agent_obj: Any, message: str, session_id: str, metadata: Dict[str, Any]) -> str:
    """
    Adapter so you can keep your agent classes as-is.
    Tries common method names.
    """
    # Try: run(message=..., session_id=..., metadata=...)
    if hasattr(agent_obj, "run") and callable(agent_obj.run):
        out = agent_obj.run(message=message, session_id=session_id, metadata=metadata)
        return out if isinstance(out, str) else str(out)

    # Try: respond(message)
    if hasattr(agent_obj, "respond") and callable(agent_obj.respond):
        out = agent_obj.respond(message)
        return out if isinstance(out, str) else str(out)

    # Try: __call__(message)
    if callable(agent_obj):
        out = agent_obj(message)
        return out if isinstance(out, str) else str(out)

    raise TypeError(f"Agent {type(agent_obj).__name__} has no callable interface (run/respond/__call__).")


@router.post("/chat", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    agents: Dict[str, Any] = Depends(get_agents),
    store: InMemoryEventStore = Depends(get_store),
) -> ChatResponse:
    session_id = req.session_id or "default"
    agent_key = req.agent or "agent_1"

    if agent_key not in agents:
        raise HTTPException(status_code=400, detail=f"Unknown agent '{agent_key}'")

    agent_obj = agents[agent_key]

    store.add(
        type="chat_request",
        session_id=session_id,
        payload={"agent": agent_key, "message": req.message, "metadata": req.metadata},
    )

    try:
        reply = _call_agent(agent_obj, req.message, session_id, req.metadata)
    except Exception as e:
        log.exception("Agent call failed")
        store.add(
            type="chat_error",
            session_id=session_id,
            payload={"agent": agent_key, "error": str(e)},
        )
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {e}")

    store.add(
        type="chat_response",
        session_id=session_id,
        payload={"agent": agent_key, "reply": reply},
    )

    return ChatResponse(session_id=session_id, agent=agent_key, reply=reply, raw={})
```

---

### FILE: `src/api/routes/dashboard.py`

```python
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends

from src.api.models import DashboardSummary
from src.api.store import InMemoryEventStore

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def get_agents() -> Dict[str, Any]:
    raise RuntimeError("Agents dependency not wired")


def get_store() -> InMemoryEventStore:
    raise RuntimeError("Store dependency not wired")


@router.get("/summary", response_model=DashboardSummary)
def summary(
    agents: Dict[str, Any] = Depends(get_agents),
    store: InMemoryEventStore = Depends(get_store),
) -> DashboardSummary:
    agents_info = {k: type(v).__name__ for k, v in agents.items()}
    return DashboardSummary(
        status="ok",
        agents=agents_info,
        total_events=store.count(),
        events_by_type=store.counts_by_type(),
    )
```

---

### FILE: `src/api/routes/insights.py`

```python
from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.models import InsightsOverview
from src.api.store import InMemoryEventStore

router = APIRouter(prefix="/api/insights", tags=["insights"])


def get_store() -> InMemoryEventStore:
    raise RuntimeError("Store dependency not wired")


@router.get("/overview", response_model=InsightsOverview)
def overview(store: InMemoryEventStore = Depends(get_store)) -> InsightsOverview:
    return InsightsOverview(
        total_events=store.count(),
        events_by_type=store.counts_by_type(),
        recent_events=store.list(limit=50),
    )
```

---

### FILE: `src/api/routes/__init__.py`

```python
from .chat import router as chat_router
from .dashboard import router as dashboard_router
from .insights import router as insights_router

__all__ = ["chat_router", "dashboard_router", "insights_router"]
```

---

### FILE: `src/api/app_factory.py`

```python
from __future__ import annotations

import logging
import time
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.api.logging_setup import configure_logging
from src.api.store import InMemoryEventStore
from src.api.routes import chat_router, dashboard_router, insights_router

log = logging.getLogger("api.app_factory")


def create_app(
    base_app: FastAPI | None,
    agents: Dict[str, Any],
    store: InMemoryEventStore,
) -> FastAPI:
    """
    If you already have an app from AgentOS (agent_os.get_app()),
    pass it as base_app. Otherwise pass None and we create one.
    """
    configure_logging()

    app = base_app or FastAPI(title="Agno Agent Backend")

    # ---- Basic request logging middleware ----
    @app.middleware("http")
    async def request_logger(request: Request, call_next):
        start = time.time()
        resp = await call_next(request)
        ms = int((time.time() - start) * 1000)
        log.info("%s %s -> %s (%dms)", request.method, request.url.path, resp.status_code, ms)
        return resp

    # ---- Dependency wiring (simple closure injection) ----
    # We patch the dependencies in route modules via their dependency funcs.
    # This keeps everything simple and avoids a big DI framework.
    from src.api.routes import chat as chat_mod
    from src.api.routes import dashboard as dash_mod
    from src.api.routes import insights as ins_mod

    chat_mod.get_agents = lambda: agents
    chat_mod.get_store = lambda: store
    dash_mod.get_agents = lambda: agents
    dash_mod.get_store = lambda: store
    ins_mod.get_store = lambda: store

    # ---- Routers ----
    app.include_router(chat_router)
    app.include_router(dashboard_router)
    app.include_router(insights_router)

    # ---- Simple health ----
    @app.get("/health")
    def health():
        return {"status": "ok"}

    # ---- Simple global error shaping (optional) ----
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        log.exception("Unhandled error: %s", exc)
        return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})

    return app
```

---

### FILE: `src/api/__init__.py`

```python
# API package
```

---

## Optional: make agent imports clean

### FILE: `src/agents/__init__.py`

(only if you want neat imports like `from src.agents import Agent1`)

```python
from .agent_1 import Agent1
from .agent_2 import Agent2
from .agent_3 import Agent3

__all__ = ["Agent1", "Agent2", "Agent3"]
```

> If your classes are named differently, adjust these names.

---

## 3) New `main.py` (temporary main)

You said you can rename your existing `main.py` to `temp_main.py`.
Here’s a clean **new** `main.py` that wires everything together.

### FILE: `main.py`

```python
from __future__ import annotations

from fastapi import FastAPI

from agno.os import AgentOS

# Import your agent classes (adjust names if needed)
# Option A: if you added src/agents/__init__.py
from src.agents import Agent1, Agent2, Agent3

from src.api.app_factory import create_app
from src.api.store import InMemoryEventStore


# ---- Instantiate agents ----
agent_1 = Agent1()
agent_2 = Agent2()
agent_3 = Agent3()

agents = {
    "agent_1": agent_1,
    "agent_2": agent_2,
    "agent_3": agent_3,
}

# ---- AgentOS ----
agent_os = AgentOS(
    description="Example app for basic agent, team and workflow",
    agents=[agent_1, agent_2, agent_3],
    # other params...
)

# AgentOS app (if it returns FastAPI/ASGI)
base_app = agent_os.get_app()

# Event store (in-memory)
store = InMemoryEventStore(max_events=5000)

# Create final app (API routers mounted onto base_app)
app: FastAPI = create_app(base_app=base_app, agents=agents, store=store)


if __name__ == "__main__":
    # Keep your serve pattern
    agent_os.serve(app="main:app", host="0.0.0.0", port=9999, reload=True)
```

---

## 4) How to run + quick test

Run (same as you do):

```bash
cd agno_agent/backend
python -m main
```

Test:

```bash
curl -X POST "http://localhost:9999/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"message":"hello","session_id":"s1","agent":"agent_1"}'
```

Dashboard:

```bash
curl "http://localhost:9999/api/dashboard/summary"
```

Insights:

```bash
curl "http://localhost:9999/api/insights/overview"
```

---

### Notes (important, but short)

* The chat endpoint uses an adapter `_call_agent()` that tries `run()`, then `respond()`, then `__call__()`.
  So your agent classes can stay mostly unchanged.
* The “logging mechanism” here is intentionally basic:

  * standard python logs
  * plus a tiny in-memory event log for dashboard/insights

If you paste your `Agent1/2/3` class method signatures (just the method names), I can align `_call_agent()` to be *exactly* correct for your agents in one shot.
