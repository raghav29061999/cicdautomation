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

    # ---- Routers ----
    app.include_router(chat_router)
    app.include_router(dashboard_router)
    app.include_router(insights_router)

    # ---- Dependency overrides (THIS is the key fix) ----
    from src.api.routes import chat as chat_mod
    from src.api.routes import dashboard as dash_mod
    from src.api.routes import insights as ins_mod

    app.dependency_overrides[chat_mod.get_agents] = lambda: agents
    app.dependency_overrides[chat_mod.get_store] = lambda: store

    app.dependency_overrides[dash_mod.get_agents] = lambda: agents
    app.dependency_overrides[dash_mod.get_store] = lambda: store

    app.dependency_overrides[ins_mod.get_store] = lambda: store

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
