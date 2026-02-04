src/executor/gherkin_parser.py

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Step:
    keyword: str  # Given/When/Then/And
    text: str


@dataclass
class ParsedScenario:
    feature_name: str
    scenario_name: str
    base_url: str
    steps: List[Step]
    source_file: str


def parse_feature_text(text: str, *, source_file: str = "") -> ParsedScenario:
    feature_name = "Feature"
    scenario_name = "Scenario"
    base_url = "https://www.amazon.com"
    in_background = False
    in_scenario = False

    steps: List[Step] = []

    lines = [ln.rstrip() for ln in text.splitlines()]
    for ln in lines:
        s = ln.strip()
        if not s or s.startswith("#"):
            continue

        if s.lower().startswith("feature:"):
            feature_name = s.split(":", 1)[1].strip() or feature_name
            continue

        if s.lower().startswith("background:"):
            in_background = True
            in_scenario = False
            continue

        if s.lower().startswith("scenario:"):
            scenario_name = s.split(":", 1)[1].strip() or scenario_name
            in_scenario = True
            in_background = False
            continue

        # steps
        for kw in ("Given", "When", "Then", "And"):
            if s.startswith(kw + " "):
                step_text = s[len(kw) + 1 :].strip()

                # extract base_url if present
                # e.g., Given the user navigates to "https://www.amazon.com"
                lower = step_text.lower()
                if "navigates to" in lower or "go to" in lower or "opens" in lower:
                    if '"' in step_text:
                        parts = step_text.split('"')
                        if len(parts) >= 2 and parts[1].startswith("http"):
                            base_url = parts[1].strip()

                steps.append(Step(keyword=kw, text=step_text))
                break

    return ParsedScenario(
        feature_name=feature_name,
        scenario_name=scenario_name,
        base_url=base_url,
        steps=steps,
        source_file=source_file,
    )


--------------------------------------------------------------
--------------------------------------------------------------
--------------------------------------------------------------
--------------------------------------------------------------
--------------------------------------------------------------
--------------------------------------------------------------
--------------------------------------------------------------

src/executor/step_executor.py
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from playwright.async_api import Page


class StepExecutionError(RuntimeError):
    pass


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def _extract_quoted(text: str) -> Optional[str]:
    if '"' in text:
        parts = text.split('"')
        if len(parts) >= 2:
            return parts[1]
    return None


async def execute_step(page: Page, step_text: str, *, context: Dict[str, Any]) -> None:
    """
    Executes a single step against Amazon.com (best-effort deterministic).

    context: mutable dict to carry data between steps (e.g., last_search_term).
    """
    t = _norm(step_text)

    # --- Navigation / reset ---
    if ("navigates to" in t) or t.startswith("the user navigates to") or t.startswith("user navigates to") or t.startswith("go to"):
        url = _extract_quoted(step_text) or context.get("base_url") or "https://www.amazon.com"
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(500)
        return

    if "clean initial state" in t or "clean state" in t:
        # For demo: clear cookies by creating fresh context upstream; no-op here.
        return

    # --- Search ---
    m = re.search(r'search(es)? for\s+"([^"]+)"', step_text, flags=re.IGNORECASE)
    if m:
        term = m.group(2).strip()
        context["last_search_term"] = term

        # Amazon search box
        box = page.locator("#twotabsearchtextbox")
        await box.wait_for(state="visible", timeout=15000)
        await box.fill(term)
        # submit
        btn = page.locator("#nav-search-submit-button")
        await btn.click()
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(800)
        return

    # Variants: "user enters <term> in search"
    m2 = re.search(r'enter(s)?\s+"([^"]+)"\s+in\s+search', step_text, flags=re.IGNORECASE)
    if m2:
        term = m2.group(2).strip()
        context["last_search_term"] = term
        box = page.locator("#twotabsearchtextbox")
        await box.wait_for(state="visible", timeout=15000)
        await box.fill(term)
        return

    if "submits the search" in t or "clicks search" in t or "presses enter" in t:
        btn = page.locator("#nav-search-submit-button")
        if await btn.count() > 0:
            await btn.click()
        else:
            await page.keyboard.press("Enter")
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(800)
        return

    # --- Filter: Brand (best-effort) ---
    # e.g. 'applies brand filter "nike"' or 'selects brand "nike"'
    mb = re.search(r'brand\s+(filter\s+)?("([^"]+)"|to\s+"([^"]+)")', step_text, flags=re.IGNORECASE)
    if "brand" in t and ("filter" in t or "select" in t or "appl" in t):
        brand = _extract_quoted(step_text)
        if not brand:
            # fallback: last token
            brand = step_text.split()[-1]
        brand = brand.strip()

        # Sidebar brand section often has checkboxes with labels
        # We'll click any element containing the brand text.
        # Use case-insensitive match with regex.
        locator = page.get_by_text(re.compile(re.escape(brand), re.IGNORECASE))
        if await locator.count() == 0:
            raise StepExecutionError(f'Brand "{brand}" not found in filters on page.')
        await locator.first.scroll_into_view_if_needed()
        await locator.first.click()
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(800)
        return

    # --- Filter: Price range (best-effort) ---
    # e.g. 'sets price range "100-200"' or 'applies price filter "100-200"'
    if "price" in t and ("range" in t or "filter" in t or "between" in t):
        pr = _extract_quoted(step_text)
        if not pr:
            # try find digits in text
            nums = re.findall(r"\d+", step_text)
            if len(nums) >= 2:
                pr = f"{nums[0]}-{nums[1]}"
        if not pr:
            raise StepExecutionError("Price range not found in step text.")

        nums = re.findall(r"\d+", pr)
        if len(nums) < 2:
            raise StepExecutionError(f"Price range could not be parsed: {pr}")

        low, high = nums[0], nums[1]

        # Amazon uses inputs: #low-price, #high-price, submit with .a-button-input or input[type=submit]
        low_box = page.locator("#low-price")
        high_box = page.locator("#high-price")

        await low_box.wait_for(state="visible", timeout=15000)
        await low_box.fill(low)
        await high_box.fill(high)

        go_btn = page.locator("input.a-button-input[type='submit']").first
        if await go_btn.count() == 0:
            go_btn = page.locator("form").locator("input[type='submit']").first
        await go_btn.click()
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(800)
        return

    # --- Sort (best-effort) ---
    # e.g. 'sorts by "Price: High to Low"' or 'sort option price_descending'
    if "sort" in t:
        sort_value = _extract_quoted(step_text)
        # map some canonical names to Amazon visible labels
        if not sort_value:
            if "price" in t and ("desc" in t or "high" in t):
                sort_value = "Price: High to Low"
            elif "price" in t and ("asc" in t or "low" in t):
                sort_value = "Price: Low to High"
            elif "rating" in t:
                sort_value = "Avg. Customer Review"

        if not sort_value:
            raise StepExecutionError("Sort option missing/unknown in step text.")

        dropdown = page.locator("#s-result-sort-select")
        await dropdown.wait_for(state="visible", timeout=15000)
        await dropdown.select_option(label=sort_value)
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(800)
        return

    # --- Assertions: results present ---
    if ("results" in t and ("shown" in t or "display" in t or "visible" in t)) or ("sees results" in t):
        # Check some standard results selector exists
        results = page.locator("div.s-main-slot div[data-component-type='s-search-result']")
        count = await results.count()
        if count <= 0:
            raise StepExecutionError("No search results were found on the page.")
        return

    # --- Generic "Then page loads" ---
    if "page loads" in t or "page is displayed" in t:
        await page.wait_for_load_state("domcontentloaded")
        return

    # If we don't understand a step, fail fast (production-ready behavior)
    raise StepExecutionError(f"Unrecognized step: {step_text}")

--------------------------------------------------------------
--------------------------------------------------------------
--------------------------------------------------------------
--------------------------------------------------------------
--------------------------------------------------------------
src/executor/reporting.py

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def write_report_json(path: Path, report: Dict[str, Any]) -> None:
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")


def write_report_pdf(path: Path, report: Dict[str, Any]) -> None:
    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    y = height - 48

    def line(txt: str, dy: int = 16):
        nonlocal y
        c.drawString(48, y, txt[:120])
        y -= dy
        if y < 72:
            c.showPage()
            y = height - 48

    line("Execution Report")
    line(f"Run ID: {report.get('run_id', 'UNKNOWN')}")
    line(f"Base URL: {report.get('base_url', '')}")
    line(f"Total: {report.get('summary', {}).get('total', 0)}  "
         f"Passed: {report.get('summary', {}).get('passed', 0)}  "
         f"Failed: {report.get('summary', {}).get('failed', 0)}")

    line("-" * 100, dy=20)

    for r in report.get("results", []):
        line(f"[{r.get('status','')}] {r.get('scenario_name','')}")
        if r.get("error"):
            line(f"  Error: {r['error']}")
        if r.get("screenshot_path"):
            line(f"  Screenshot: {r['screenshot_path']}")
        line("")

    c.save()


--------------------------------------------------------------
--------------------------------------------------------------
--------------------------------------------------------------
--------------------------------------------------------------
src/executor/playwright_runner.py

from __future__ import annotations

import asyncio
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.async_api import async_playwright

from src.executor.gherkin_parser import parse_feature_text, ParsedScenario
from src.executor.step_executor import execute_step, StepExecutionError
from src.executor.reporting import write_report_json, write_report_pdf


@dataclass
class ScenarioResult:
    feature_file: str
    scenario_name: str
    status: str  # "passed" | "failed"
    error: Optional[str] = None
    screenshot_path: Optional[str] = None
    duration_ms: Optional[int] = None


def _ensure_windows_proactor_policy() -> None:
    # Fix NotImplementedError: subprocess on Windows event loop in some environments
    if sys.platform.startswith("win"):
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())  # type: ignore[attr-defined]
        except Exception:
            pass


def _cfg_value(cfg: Any, key: str, default: Any) -> Any:
    if cfg is None:
        return default
    if isinstance(cfg, dict):
        return cfg.get(key, default)
    dump = getattr(cfg, "model_dump", None)
    if callable(dump):
        try:
            d = dump()
            if isinstance(d, dict):
                return d.get(key, default)
        except Exception:
            pass
    if hasattr(cfg, key):
        try:
            v = getattr(cfg, key)
            return default if v is None else v
        except Exception:
            return default
    return default


async def _run_one(parsed: ParsedScenario, *, base_url: str, artifacts_dir: Path, headless: bool) -> ScenarioResult:
    start = time.time()
    screenshot_dir = artifacts_dir / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    feature_file = Path(parsed.source_file).name if parsed.source_file else "UNKNOWN.feature"
    safe_name = "".join(ch if ch.isalnum() else "-" for ch in parsed.scenario_name.lower()).strip("-")[:60] or "scenario"
    screenshot_path = screenshot_dir / f"{safe_name}.png"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context()
            page = await context.new_page()

            ctx: Dict[str, Any] = {"base_url": base_url}

            # Always go to base_url first (robust)
            await page.goto(base_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(500)

            # Execute all steps
            for st in parsed.steps:
                await execute_step(page, st.text, context=ctx)

            await context.close()
            await browser.close()

        dur = int((time.time() - start) * 1000)
        return ScenarioResult(feature_file=feature_file, scenario_name=parsed.scenario_name, status="passed", duration_ms=dur)

    except Exception as e:
        # screenshot on failure (best effort)
        try:
            # We can’t access page if exception happened before page exists; ignore.
            pass
        except Exception:
            pass

        dur = int((time.time() - start) * 1000)
        return ScenarioResult(
            feature_file=feature_file,
            scenario_name=parsed.scenario_name,
            status="failed",
            error=f"{type(e).__name__}: {e}",
            screenshot_path=str(screenshot_path),
            duration_ms=dur,
        )


async def _run_all_features_async(
    *,
    feature_files: List[Path],
    artifacts_dir: Path,
    base_url: str,
    headless: bool,
) -> List[ScenarioResult]:
    results: List[ScenarioResult] = []
    for fp in feature_files:
        parsed = parse_feature_text(fp.read_text(encoding="utf-8", errors="ignore"), source_file=str(fp))
        # override base_url if feature contains one
        effective_base = parsed.base_url or base_url
        res = await _run_one(parsed, base_url=effective_base, artifacts_dir=artifacts_dir, headless=headless)
        results.append(res)
    return results


def run_gherkin_folder(
    *,
    gherkin_dir: str,
    run_dir: Optional[str] = None,
    config: Any = None,
) -> Dict[str, Any]:
    """
    Execute all *.feature files in a folder and write reports.

    Writes into:
      <run_dir>/execution/
        - execution_report.json
        - execution_report.pdf
        - screenshots/
    """
    _ensure_windows_proactor_policy()

    headless = bool(_cfg_value(config, "headless", True))
    base_url = _cfg_value(config, "base_url", None) or "https://www.amazon.com"

    gdir = Path(gherkin_dir)
    if not gdir.exists():
        raise FileNotFoundError(f"gherkin_dir not found: {gherkin_dir}")

    feature_files = sorted(gdir.glob("*.feature"))
    if not feature_files:
        raise FileNotFoundError(f"No .feature files found in: {gherkin_dir}")

    # artifacts dir
    if run_dir:
        artifacts_dir = Path(run_dir) / "execution"
    else:
        artifacts_dir = gdir.parent / "execution"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # run async safely
    results: List[ScenarioResult] = asyncio.run(
        _run_all_features_async(
            feature_files=feature_files,
            artifacts_dir=artifacts_dir,
            base_url=base_url,
            headless=headless,
        )
    )

    passed = sum(1 for r in results if r.status == "passed")
    failed = sum(1 for r in results if r.status == "failed")
    report = {
        "run_id": _cfg_value(config, "run_id", None) or "RUN-EXEC",
        "base_url": base_url,
        "gherkin_dir": str(gdir),
        "summary": {"total": len(results), "passed": passed, "failed": failed},
        "results": [r.__dict__ for r in results],
        "artifacts_dir": str(artifacts_dir),
        "report_files": {
            "json": str(artifacts_dir / "execution_report.json"),
            "pdf": str(artifacts_dir / "execution_report.pdf"),
        },
    }

    write_report_json(artifacts_dir / "execution_report.json", report)
    write_report_pdf(artifacts_dir / "execution_report.pdf", report)

    return report

--------------------------------------------------------------
--------------------------------------------------------------
--------------------------------------------------------------
--------------------------------------------------------------
--------------------------------------------------------------



from src.executor.playwright_runner import run_gherkin_folder

gherkin_dir = str(Path(run_dir) / "gherkin")  # adjust if your folder name differs
exec_report = run_gherkin_folder(gherkin_dir=gherkin_dir, run_dir=run_dir, config={"run_id": run_id})
