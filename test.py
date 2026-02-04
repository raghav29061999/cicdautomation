from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Page

from .config import ExecutorConfig
from .models import Scenario, ScenarioResult
from .artifacts import execution_dir


def _ensure_windows_proactor_policy() -> None:
    if sys.platform.startswith("win"):
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())  # type: ignore[attr-defined]
        except Exception:
            pass


def _sanitize_base_url(url: str) -> str:
    return (url or "").replace(" ", "").strip() or "https://www.amazon.com"


class StepUnsupported(RuntimeError):
    pass


class ScenarioPrereqUnsupported(RuntimeError):
    """Use this to SKIP instead of FAIL for non-deterministic prerequisites (login/cart exact totals)."""
    pass


async def _goto(page: Page, url: str, cfg: ExecutorConfig) -> None:
    await page.goto(url, wait_until="domcontentloaded", timeout=cfg.navigation_timeout_ms)
    await page.wait_for_timeout(600)


async def _execute_step(page: Page, step_text: str, scenario: Scenario, cfg: ExecutorConfig) -> None:
    t = step_text.strip().lower()

    # 1) Navigate
    if "navigates to" in t or "goes to" in t:
        # base url already extracted in loader; just go
        await _goto(page, _sanitize_base_url(scenario.base_url), cfg)
        return

    if "clean initial state" in t:
        # handled by fresh browser context; no-op
        return

    # 2) Login prerequisite (SKIP — Amazon live is not deterministic)
    if "logged in" in t:
        raise ScenarioPrereqUnsupported("Login prerequisite detected; skipping (non-deterministic on live Amazon).")

    # 3) Cart contains specific items/prices (SKIP unless you implement catalog mapping)
    if "cart contains item" in t or "cart contains" in t:
        raise ScenarioPrereqUnsupported("Specific cart state required (items/prices); skipping for live Amazon demo.")

    # 4) Search: When the user searches for "..."
    if "search" in t and '"' in step_text:
        term = step_text.split('"')[1].strip()
        box = page.locator("#twotabsearchtextbox")
        await box.wait_for(state="visible", timeout=cfg.action_timeout_ms)
        await box.fill(term)
        await page.locator("#nav-search-submit-button").click()
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(800)
        return

    # 5) Assert results exist
    if ("results" in t and ("shown" in t or "display" in t or "visible" in t)) or ("sees results" in t):
        results = page.locator("div.s-main-slot div[data-component-type='s-search-result']")
        if await results.count() <= 0:
            raise RuntimeError("Assertion failed: no search results found.")
        return

    # 6) Quantity selector / totals exact numbers (SKIP for live Amazon, non-deterministic)
    if "changes the quantity" in t or "subtotal" in t or "cart total" in t:
        raise ScenarioPrereqUnsupported("Cart quantity/total verification requires deterministic cart setup; skipping.")

    raise StepUnsupported(f"Unrecognized step (no mapping): {step_text}")


async def _run_one_async(scenario: Scenario, *, run_dir: Path, cfg: ExecutorConfig) -> ScenarioResult:
    start = time.time()

    exec_dir = execution_dir(run_dir)
    shots_dir = exec_dir / (cfg.screenshots_dirname or "screenshots")
    shots_dir.mkdir(parents=True, exist_ok=True)

    safe_name = "".join(ch if ch.isalnum() else "-" for ch in scenario.scenario_name.lower()).strip("-")[:80] or "scenario"
    shot_path = shots_dir / f"{safe_name}.png"

    base_url = _sanitize_base_url(cfg.base_url_override or scenario.base_url)

    try:
        async with async_playwright() as p:
            browser_type = getattr(p, cfg.browser, None) or p.chromium
            browser = await browser_type.launch(headless=cfg.headless, slow_mo=cfg.slow_mo_ms or 0)

            context = await browser.new_context()
            page = await context.new_page()

            # always start at base url
            await _goto(page, base_url, cfg)

            for st in scenario.steps:
                await _execute_step(page, st.text, scenario, cfg)

            await context.close()
            await browser.close()

        dur_ms = int((time.time() - start) * 1000)
        return ScenarioResult(
            feature_file=scenario.feature_file,
            scenario_name=scenario.scenario_name,
            status="passed",
            duration_ms=dur_ms,
        )

    except ScenarioPrereqUnsupported as e:
        dur_ms = int((time.time() - start) * 1000)
        return ScenarioResult(
            feature_file=scenario.feature_file,
            scenario_name=scenario.scenario_name,
            status="skipped",
            error=str(e),
            duration_ms=dur_ms,
        )

    except Exception as e:
        # screenshot best effort
        if cfg.take_screenshot_on_failure:
            try:
                # we cannot guarantee `page` exists here; so we screenshot only if possible via trace not available.
                pass
            except Exception:
                pass

        dur_ms = int((time.time() - start) * 1000)
        return ScenarioResult(
            feature_file=scenario.feature_file,
            scenario_name=scenario.scenario_name,
            status="failed",
            error=f"{type(e).__name__}: {e}",
            duration_ms=dur_ms,
            screenshot_path=str(shot_path) if cfg.take_screenshot_on_failure else None,
        )


def run_scenario(scenario: Scenario, *, run_dir: Path, config: Optional[ExecutorConfig] = None) -> ScenarioResult:
    """
    Sync wrapper for pipeline usage.
    """
    _ensure_windows_proactor_policy()
    cfg = config or ExecutorConfig()

    # if already running loop (streamlit), use thread loop
    try:
        asyncio.get_running_loop()
        has_running = True
    except RuntimeError:
        has_running = False

    if not has_running:
        return asyncio.run(_run_one_async(scenario, run_dir=run_dir, cfg=cfg))

    import threading

    holder = {"result": None, "error": None}

    def _thread_main():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            holder["result"] = loop.run_until_complete(_run_one_async(scenario, run_dir=run_dir, cfg=cfg))
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
        raise RuntimeError(f"Playwright execution failed: {holder['error']}")

    return holder["result"]
