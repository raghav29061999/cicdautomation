# src/utils/logging.py
from __future__ import annotations

import logging
import os
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional


LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def get_run_logger(
    *,
    run_id: str,
    run_dir: str | Path,
    name: str = "agentic",
    level: int = logging.INFO,
) -> logging.Logger:
    """
    Returns a logger that logs to:
      - runtime/runs/<run_id>/logs/run.log
      - stdout

    Safe to call multiple times: handlers won't duplicate.
    """
    run_dir_p = Path(run_dir)
    logs_dir = run_dir_p / "logs"
    _ensure_dir(logs_dir)

    log_path = logs_dir / "run.log"

    logger_name = f"{name}.{run_id}"
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)
    logger.propagate = False  # prevent double logging via root

    # Avoid duplicate handlers if called again
    if getattr(logger, "_configured", False):
        return logger

    formatter = logging.Formatter(LOG_FORMAT)

    # File handler
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # Console handler
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(level)
    sh.setFormatter(formatter)
    logger.addHandler(sh)

    logger._configured = True  # type: ignore[attr-defined]
    logger.info("Logger initialized. log_file=%s", str(log_path))
    return logger


@dataclass
class StepResult:
    step: str
    status: str  # success|failure
    duration_ms: int
    error: Optional[str] = None


@contextmanager
def log_step(logger: logging.Logger, step_name: str) -> Iterator[None]:
    """
    Context manager for step-level logging with timing + exception capture.
    """
    start = time.time()
    logger.info("STEP_START | %s", step_name)
    try:
        yield
        dur = int((time.time() - start) * 1000)
        logger.info("STEP_END   | %s | status=success | duration_ms=%d", step_name, dur)
    except Exception as e:
        dur = int((time.time() - start) * 1000)
        logger.exception(
            "STEP_END   | %s | status=failure | duration_ms=%d | error=%s: %s",
            step_name,
            dur,
            type(e).__name__,
            e,
        )
        raise


def attach_logger_to_state(state: dict, logger: logging.Logger) -> dict:
    """
    Convenience: store logger in pipeline state. (Not JSON-serializable; runtime only.)
    """
    state["logger"] = logger
    return state
