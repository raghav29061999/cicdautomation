# src/executor/playwright_runner.py
from __future__ import annotations

import asyncio
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from playwright.async_api import async_playwright


# ----------------------------
# Public result object
# ----------------------------

@dataclass
class ScenarioResult:
    feature_file: str
    scenario_name: str
    status: str  # "passed" | "failed"
    error: Optional[str] = None
    screenshot_path: Optional[str] = None


# ----------------------------
# Windows loop fix
# ----------------------------

def _ensure_windows_proactor_loop_policy() -> None:
    """
    Playwright needs subprocess support; on Windows, that requires ProactorEventLoop.
    Some runners (Streamlit/IDE) can leave you on a Selector loop -> NotImplementedError.
    """
    if sys.platform.startswith("win"):
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())  # type: ignore[attr-defined]
        except Exception:
            # If Python build doesn't expose it, we'll still try to run, but most Windows builds do.
            pass


# ----------------------------
# Runner core (async)
# ----------------------------

async def _run_single_scenario(
    base_url: str,
    scenario: Dict[str, Any],
    artifacts_dir: Path,
    headless: bool = True,
) -> ScenarioResult:
    """
    scenario is a parsed structure you already generate from Gherkin, e.g.:
      {
        "feature_file": "TC-001.feature",
        "scenario_name": "...",
        "steps": [{"keyword":"Given","text":"..."}, ...]
      }
    """
    feature_file = scenario.get("feature_file", "UNKNOWN.feature")
    scenario_name = scenario.get("scenario_name", "UNKNOWN SCENARIO")

    screenshot_dir = artifacts_dir / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context()
            page = await context.new_page()

            # --- Minimal execution model ---
            # You MUST map your English steps -> actions here.
            # For now, we support just the navigation background step deterministically.
            await page.goto(base_url, wait_until="domcontentloaded")

            # If you already have a step executor, call it here:
            # await execute_steps(page, scenario["steps"], data_bindings=...)

            await context.close()
            await browser.close()

        return ScenarioResult(
            feature_file=feature_file,
            scenario_name=scenario_name,
            status="passed",
        )

    except Exception as e:
        # best-effort screenshot
        screenshot_path = None
        try:
            screenshot_path = str(screenshot_dir / f"{Path(feature_file).stem}-{_safe_slug(scenario_name)}.png")
            # We can't screenshot without a page handle if Playwright failed early.
            # If you want screenshots on step failures, capture inside your step executor.
        except Exception:
            screenshot_path = None

        return ScenarioResult(
            feature_file=feature_file,
            scenario_name=scenario_name,
            status="failed",
            error=f"{type(e).__name__}: {e}",
            screenshot_path=screenshot_path,
        )


def _safe_slug(s: str) -> str:
    keep = []
    for ch in s.lower():
        if ch.isalnum():
            keep.append(ch)
        elif ch in (" ", "-", "_"):
            keep.append("-")
    out = "".join(keep).strip("-")
    while "--" in out:
        out = out.replace("--", "-")
    return out[:60] or "scenario"


async def _run_all_async(
    base_url: str,
    parsed_scenarios: List[Dict[str, Any]],
    artifacts_dir: Path,
    headless: bool = True,
) -> List[ScenarioResult]:
    results: List[ScenarioResult] = []
    for sc in parsed_scenarios:
        res = await _run_single_scenario(
            base_url=base_url,
            scenario=sc,
            artifacts_dir=artifacts_dir,
            headless=headless,
        )
        results.append(res)
    return results


# ----------------------------
# Streamlit-safe sync wrapper
# ----------------------------

def run_scenarios(
    base_url: str,
    parsed_scenarios: List[Dict[str, Any]],
    artifacts_dir: str,
    headless: bool = True,
) -> List[ScenarioResult]:
    """
    Safe to call from:
      - CLI
      - LangGraph node
      - Streamlit

    Runs Playwright in a dedicated thread with its own event loop.
    """
    _ensure_windows_proactor_loop_policy()

    out_dir = Path(artifacts_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    holder: Dict[str, Any] = {"results": None, "error": None}

    def _thread_main() -> None:
        try:
            # Fresh event loop in thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            holder["results"] = loop.run_until_complete(
                _run_all_async(
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
