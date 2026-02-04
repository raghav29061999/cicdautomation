# src/executor/playwright_runner.py

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional


def _cfg_value(cfg: Any, key: str, default: Any) -> Any:
    """
    Read config from dict OR object (pydantic/dataclass/any object with attributes).
    """
    if cfg is None:
        return default

    # dict-like
    if isinstance(cfg, dict):
        return cfg.get(key, default)

    # pydantic v2 BaseModel -> model_dump
    dump = getattr(cfg, "model_dump", None)
    if callable(dump):
        try:
            d = dump()
            if isinstance(d, dict):
                return d.get(key, default)
        except Exception:
            pass

    # dataclass-like / object attribute
    if hasattr(cfg, key):
        try:
            v = getattr(cfg, key)
            return default if v is None else v
        except Exception:
            return default

    return default


def run_scenarios(
    parsed_scenarios: List[Dict[str, Any]],
    *,
    base_url: Optional[str] = None,
    artifacts_dir: Optional[str] = None,
    run_dir: Optional[str] = None,
    config: Any = None,  # <-- dict OR ExecutorConfig OR pydantic model
) -> List[Any]:
    """
    Compatible entrypoint for pipeline/UI.

    Accepts:
      - run_dir + config (common in nodes)
      - artifacts_dir directly (executor-only)
      - base_url optional (defaults to amazon)
    """

    # ---- resolve artifacts directory ----
    if artifacts_dir is None and run_dir is not None:
        artifacts_dir = str(Path(run_dir) / "execution")

    if artifacts_dir is None:
        raise ValueError("artifacts_dir or run_dir must be provided")

    out_dir = Path(artifacts_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---- resolve base_url ----
    if base_url is None:
        base_url = _cfg_value(config, "base_url", None) or "https://www.amazon.com"

    # ---- config handling (safe defaults) ----
    headless = bool(_cfg_value(config, "headless", True))

    holder: Dict[str, Any] = {"results": None, "error": None}

    def _thread_main() -> None:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            holder["results"] = loop.run_until_complete(
                _run_all_async(  # <-- keep your existing async implementation
                    base_url=base_url,
                    parsed_scenarios=parsed_scenarios,
                    artifacts_dir=out_dir,
                    headless=headless,
                )
            )
        except Exception as e:
            holder["error"] = e
        finally:
            try:
                loop.close()
            except Exception:
                pass

    t = threading.Thread(target=_thread_main, daemon=True)
    t.start()
    t.join()

    if holder["error"] is not None:
        e = holder["error"]
        raise RuntimeError(f"Playwright execution failed: {type(e).__name__}: {e}")

    return holder["results"] or []
