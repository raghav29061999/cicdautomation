src/pipeline/nodes.py

from pathlib import Path

from src.executor.run_manager import run_features
from src.executor.config import ExecutorConfig


def node_execute_gherkin(state: dict) -> dict:
    """
    Execute generated Gherkin files using Playwright executor.
    Produces:
      runtime/runs/<run_id>/execution/report.json
      runtime/runs/<run_id>/execution/report.pdf
    """
    run_id = state.get("run_id") or "UNKNOWN"
    run_dir = state.get("run_dir")
    if not run_dir:
        raise RuntimeError("node_execute_gherkin: run_dir missing in state.")

    run_dir_p = Path(run_dir)
    if not run_dir_p.exists():
        raise RuntimeError(f"node_execute_gherkin: run_dir not found: {run_dir}")

    # Find gherkin folder (support common variants)
    candidates = [
        run_dir_p / "gherkin",
        run_dir_p / "features",
        run_dir_p / "gherkin_files",
        run_dir_p,  # last resort
    ]
    gherkin_dir = None
    for c in candidates:
        if c.exists() and any(c.glob("*.feature")):
            gherkin_dir = c
            break

    if gherkin_dir is None:
        raise RuntimeError(f"node_execute_gherkin: No .feature files found under {run_dir_p}")

    # Config – keep it simple + fast
    cfg = ExecutorConfig(
        headless=True,
        browser="chromium",
        slow_mo_ms=0,
        stop_on_first_failure=False,
    )

    # If you want to enforce amazon.com for your first use-case:
    base_url_override = state.get("base_url_override") or "https://www.amazon.com"

    limit_files = int(state.get("execution_limit_files") or 0)  # 0 => all

    report = run_features(
        run_id=run_id,
        run_dir=run_dir_p,
        gherkin_dir=gherkin_dir,
        config=cfg,
        limit_files=limit_files,
        base_url_override=base_url_override,
    )

    execution_dir = run_dir_p / "execution"
    report_json = execution_dir / "report.json"
    report_pdf = execution_dir / "report.pdf"

    # Write minimal state outputs for UI
    state["execution_report_summary"] = report.to_dict().get("summary", {})
    state["execution_report_json_path"] = str(report_json)
    state["execution_report_pdf_path"] = str(report_pdf)

    return state

-------------------------------------------------------------------------------------------------------------------------------
src/pipeline/graph.py

g.add_node("execute_gherkin", n.node_execute_gherkin)

generate_gherkin -> write_gherkin -> END  -- to change

g.add_edge("write_gherkin", "execute_gherkin")
g.add_edge("execute_gherkin", END)


g.add_edge("write_test_cases", "generate_gherkin")
g.add_edge("generate_gherkin", "write_gherkin")

g.add_edge("write_gherkin", "execute_gherkin")
g.add_edge("execute_gherkin", END)



-------------------------------------------------------------------------------------------------------------------------------
src/ui/pages/studio.py

Inside _render_downloads(run_dir) add:

report_json = p / "execution" / "report.json"
report_pdf = p / "execution" / "report.pdf"


And add buttons (maybe a second row): ------

st.subheader("Execution Reports")
c1, c2 = st.columns(2)

with c1:
    if report_json.exists():
        st.download_button(
            "⬇️ Execution report.json",
            data=report_json.read_bytes(),
            file_name="report.json",
            mime="application/json",
            use_container_width=True,
            key="dl_exec_report_json",
        )
    else:
        st.caption("report.json not found.")

with c2:
    if report_pdf.exists():
        st.download_button(
            "⬇️ Execution report.pdf",
            data=report_pdf.read_bytes(),
            file_name="report.pdf",
            mime="application/pdf",
            use_container_width=True,
            key="dl_exec_report_pdf",
        )
    else:
        st.caption("report.pdf not found.")

##############
-------------------------------------------------------------------------------------------------------------------------------
src/ui/app.py

In _run_pipeline(...), return the two paths in result dict:

return {
    "run_id": final_state.get("run_id"),
    "run_dir": final_state.get("run_dir"),
    "warnings": final_state.get("warnings", []),
    "execution_report_json_path": final_state.get("execution_report_json_path"),
    "execution_report_pdf_path": final_state.get("execution_report_pdf_path"),
}

-------------------------------------------------------------------------------------------------------------------------------

src/executor/step_registry.py

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Pattern, Tuple

# Playwright types are runtime-only; avoid typing import to keep module import-safe.


@dataclass(frozen=True)
class StepHandler:
    pattern: Pattern[str]
    name: str
    fn: Callable[..., None]


def _clean(s: str) -> str:
    return (s or "").strip()


def build_step_registry() -> List[StepHandler]:
    """
    Minimal step set to get you executing quickly.

    Conventions supported:
    - Navigate:
      Given the user navigates to "<url>"
      And the user navigates to "<url>"

    - Click:
      When the user clicks "<text>"
      When the user clicks button "<text>"
      When the user clicks link "<text>"

    - Type:
      When the user enters "<value>" into "<field>"
      When the user types "<value>" into "<field>"

      Field matching uses (first match wins):
        1) get_by_label(field)
        2) get_by_placeholder(field)
        3) locator(f'input[name="{field}"]')
        4) locator(f'input#{field}')

    - Assertions:
      Then the user should see "<text>"
      Then the page url should contain "<fragment>"
      Then the page title should contain "<text>"

    - Wait:
      And the system waits "<ms>" ms
      And the system waits "<seconds>" seconds
    """

    handlers: List[StepHandler] = []

    def navigate(page, url: str):
        page.goto(url, wait_until="domcontentloaded")

    handlers.append(
        StepHandler(
            pattern=re.compile(r'^the user navigates to\s+"([^"]+)"$', re.IGNORECASE),
            name="navigate_to",
            fn=lambda ctx, m: navigate(ctx["page"], _clean(m.group(1))),
        )
    )

    def click_by_text(page, text: str):
        # Try common roles first; fallback to text locator
        t = _clean(text)
        # Try button
        btn = page.get_by_role("button", name=t)
        if btn.count() > 0:
            btn.first.click()
            return
        # Try link
        lnk = page.get_by_role("link", name=t)
        if lnk.count() > 0:
            lnk.first.click()
            return
        # Fallback exact text
        page.get_by_text(t, exact=True).first.click()

    handlers.append(
        StepHandler(
            pattern=re.compile(r'^the user clicks\s+"([^"]+)"$', re.IGNORECASE),
            name="click_text",
            fn=lambda ctx, m: click_by_text(ctx["page"], m.group(1)),
        )
    )
    handlers.append(
        StepHandler(
            pattern=re.compile(r'^the user clicks (?:button|link)\s+"([^"]+)"$', re.IGNORECASE),
            name="click_role_text",
            fn=lambda ctx, m: click_by_text(ctx["page"], m.group(1)),
        )
    )

    def type_into(page, value: str, field: str):
        v = _clean(value)
        f = _clean(field)

        # 1) label
        loc = page.get_by_label(f)
        if loc.count() > 0:
            loc.first.fill(v)
            return

        # 2) placeholder
        loc = page.get_by_placeholder(f)
        if loc.count() > 0:
            loc.first.fill(v)
            return

        # 3) name attr
        loc = page.locator(f'input[name="{f}"]')
        if loc.count() > 0:
            loc.first.fill(v)
            return

        # 4) id
        loc = page.locator(f'input#{f}')
        if loc.count() > 0:
            loc.first.fill(v)
            return

        # fallback: any input near text? keep simple: try text match then next input
        label = page.get_by_text(f, exact=True)
        if label.count() > 0:
            # attempt to find input in same container
            container = label.first.locator("xpath=ancestor::*[self::label or self::div or self::section][1]")
            inp = container.locator("input")
            if inp.count() > 0:
                inp.first.fill(v)
                return

        raise RuntimeError(f'Unable to find field "{f}" to type into.')

    handlers.append(
        StepHandler(
            pattern=re.compile(r'^the user (?:enters|types)\s+"([^"]+)"\s+into\s+"([^"]+)"$', re.IGNORECASE),
            name="type_into",
            fn=lambda ctx, m: type_into(ctx["page"], m.group(1), m.group(2)),
        )
    )

    def assert_see_text(page, text: str):
        t = _clean(text)
        # Visible check: at least one match
        loc = page.get_by_text(t)
        if loc.count() == 0:
            raise AssertionError(f'Text not found on page: "{t}"')

    handlers.append(
        StepHandler(
            pattern=re.compile(r'^the user should see\s+"([^"]+)"$', re.IGNORECASE),
            name="assert_see_text",
            fn=lambda ctx, m: assert_see_text(ctx["page"], m.group(1)),
        )
    )

    def assert_url_contains(page, fragment: str):
        f = _clean(fragment)
        if f not in (page.url or ""):
            raise AssertionError(f'URL did not contain "{f}". Actual: {page.url}')

    handlers.append(
        StepHandler(
            pattern=re.compile(r'^the page url should contain\s+"([^"]+)"$', re.IGNORECASE),
            name="assert_url_contains",
            fn=lambda ctx, m: assert_url_contains(ctx["page"], m.group(1)),
        )
    )

    def assert_title_contains(page, text: str):
        t = _clean(text)
        title = page.title()
        if t.lower() not in (title or "").lower():
            raise AssertionError(f'Title did not contain "{t}". Actual: {title}')

    handlers.append(
        StepHandler(
            pattern=re.compile(r'^the page title should contain\s+"([^"]+)"$', re.IGNORECASE),
            name="assert_title_contains",
            fn=lambda ctx, m: assert_title_contains(ctx["page"], m.group(1)),
        )
    )

    def wait_ms(page, ms: int):
        page.wait_for_timeout(ms)

    handlers.append(
        StepHandler(
            pattern=re.compile(r'^the system waits\s+"(\d+)"\s*ms$', re.IGNORECASE),
            name="wait_ms",
            fn=lambda ctx, m: wait_ms(ctx["page"], int(m.group(1))),
        )
    )
    handlers.append(
        StepHandler(
            pattern=re.compile(r'^the system waits\s+"(\d+)"\s*seconds$', re.IGNORECASE),
            name="wait_seconds",
            fn=lambda ctx, m: wait_ms(ctx["page"], int(m.group(1)) * 1000),
        )
    )

    return handlers


def find_handler(registry: List[StepHandler], step_text: str) -> Tuple[StepHandler, re.Match[str]]:
    text = step_text.strip()
    for h in registry:
        m = h.pattern.match(text)
        if m:
            return h, m
    raise KeyError(f"No step handler matched: {text}")






-------------------------------------------------------------------------------------------------------------------------------
src/executor/artifacts.py

from __future__ import annotations

from pathlib import Path
from typing import Optional


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def execution_dir(run_dir: Path) -> Path:
    return ensure_dir(run_dir / "execution")


def screenshots_dir(run_dir: Path, dirname: str = "screenshots") -> Path:
    return ensure_dir(execution_dir(run_dir) / dirname)


def safe_filename(name: str) -> str:
    keep = []
    for ch in name:
        if ch.isalnum() or ch in ("-", "_", "."):
            keep.append(ch)
        else:
            keep.append("_")
    return "".join(keep)[:180]


def write_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")


def write_bytes(path: Path, data: bytes) -> None:
    ensure_dir(path.parent)
    path.write_bytes(data)


-------------------------------------------------------------------------------------------------------------------------------
src/executor/playwright_runner.py

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.sync_api import sync_playwright

from .artifacts import screenshots_dir, safe_filename
from .config import ExecutorConfig
from .models import Scenario, ScenarioResult
from .step_registry import build_step_registry, find_handler


def run_scenario(
    scenario: Scenario,
    run_dir: Path,
    config: ExecutorConfig,
) -> ScenarioResult:
    """
    Execute one scenario with Playwright (sync).
    """
    registry = build_step_registry()
    start = time.time()

    # Base URL selection
    base_url = config.base_url_override or scenario.base_url or "BASE_URL"

    screenshot_path: Optional[str] = None
    step_results: List[Dict[str, Any]] = []

    def _record_step(keyword: str, text: str, status: str, err: Optional[str] = None):
        item: Dict[str, Any] = {"keyword": keyword, "text": text, "status": status}
        if err:
            item["error"] = err
        step_results.append(item)

    try:
        with sync_playwright() as p:
            browser_type = getattr(p, config.browser)
            browser = browser_type.launch(headless=config.headless, slow_mo=config.slow_mo_ms)
            context = browser.new_context()
            page = context.new_page()
            page.set_default_navigation_timeout(config.navigation_timeout_ms)
            page.set_default_timeout(config.action_timeout_ms)

            ctx = {"page": page, "base_url": base_url}

            # Run background steps first
            for st in scenario.background_steps:
                full_text = st.text.replace("<base_url>", base_url)
                try:
                    handler, m = find_handler(registry, full_text)
                    handler.fn(ctx, m)
                    _record_step(st.keyword, st.text, "passed")
                except Exception as e:
                    _record_step(st.keyword, st.text, "failed", f"{type(e).__name__}: {e}")
                    raise

            # Run scenario steps
            for st in scenario.steps:
                full_text = st.text.replace("<base_url>", base_url)
                try:
                    handler, m = find_handler(registry, full_text)
                    handler.fn(ctx, m)
                    _record_step(st.keyword, st.text, "passed")
                except Exception as e:
                    _record_step(st.keyword, st.text, "failed", f"{type(e).__name__}: {e}")
                    raise

            context.close()
            browser.close()

        dur_ms = int((time.time() - start) * 1000)
        return ScenarioResult(
            file_path=scenario.file_path,
            feature_name=scenario.feature_name,
            scenario_name=scenario.scenario_name,
            status="passed",
            duration_ms=dur_ms,
            step_results=step_results,
        )

    except Exception as e:
        dur_ms = int((time.time() - start) * 1000)

        if config.take_screenshot_on_failure:
            try:
                # best-effort screenshot: run a minimal playwright context to open base and screenshot
                # NOTE: If failure happened mid-run, we might not have page handle here.
                # To keep it simple/deterministic, we take screenshot of blank base_url.
                with sync_playwright() as p:
                    browser_type = getattr(p, config.browser)
                    browser = browser_type.launch(headless=True)
                    context = browser.new_context()
                    page = context.new_page()
                    page.goto(base_url, wait_until="domcontentloaded")
                    ss_dir = screenshots_dir(run_dir, config.screenshots_dirname)
                    fname = safe_filename(f"{Path(scenario.file_path).stem}.png")
                    out = ss_dir / fname
                    page.screenshot(path=str(out), full_page=True)
                    screenshot_path = str(out)
                    context.close()
                    browser.close()
            except Exception:
                screenshot_path = None

        return ScenarioResult(
            file_path=scenario.file_path,
            feature_name=scenario.feature_name,
            scenario_name=scenario.scenario_name,
            status="failed",
            duration_ms=dur_ms,
            error_type=type(e).__name__,
            error_message=str(e),
            screenshot_path=screenshot_path,
            step_results=step_results,
        )



-------------------------------------------------------------------------------------------------------------------------------
src/executor/run_manager.py

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .config import ExecutorConfig
from .gherkin_loader import load_scenarios_from_dir
from .models import ExecutionReport, ScenarioResult
from .playwright_runner import run_scenario
from .reporter_json import write_report_json
from .reporter_pdf import write_report_pdf
from .artifacts import execution_dir


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_features(
    run_id: str,
    run_dir: Path,
    gherkin_dir: Path,
    config: Optional[ExecutorConfig] = None,
    limit_files: int = 0,
    base_url_override: Optional[str] = None,
) -> ExecutionReport:
    """
    Execute .feature files (1 scenario per file).
    - limit_files: 0 means run all; otherwise run first N files (sorted).
    """
    cfg = config or ExecutorConfig()
    if base_url_override:
        cfg = ExecutorConfig(
            headless=cfg.headless,
            browser=cfg.browser,
            slow_mo_ms=cfg.slow_mo_ms,
            navigation_timeout_ms=cfg.navigation_timeout_ms,
            action_timeout_ms=cfg.action_timeout_ms,
            base_url_override=base_url_override,
            take_screenshot_on_failure=cfg.take_screenshot_on_failure,
            screenshots_dirname=cfg.screenshots_dirname,
            stop_on_first_failure=cfg.stop_on_first_failure,
        )

    started = utc_now_iso()
    scenarios = load_scenarios_from_dir(gherkin_dir)

    if limit_files and limit_files > 0:
        scenarios = scenarios[:limit_files]

    results: List[ScenarioResult] = []
    passed = failed = skipped = 0

    # ensure execution folder exists
    _ = execution_dir(run_dir)

    base_used = cfg.base_url_override or (scenarios[0].base_url if scenarios else "BASE_URL")

    for sc in scenarios:
        # if cfg override is set, runner will use it anyway
        r = run_scenario(sc, run_dir=run_dir, config=cfg)
        results.append(r)
        if r.status == "passed":
            passed += 1
        elif r.status == "failed":
            failed += 1
            if cfg.stop_on_first_failure:
                break
        else:
            skipped += 1

    finished = utc_now_iso()

    report = ExecutionReport(
        run_id=run_id,
        run_dir=str(run_dir),
        started_at_utc=started,
        finished_at_utc=finished,
        base_url_used=base_used,
        total=len(results),
        passed=passed,
        failed=failed,
        skipped=skipped,
        results=results,
    )

    # Write outputs
    write_report_json(run_dir, report)
    write_report_pdf(run_dir, report)

    return report



-------------------------------------------------------------------------------------------------------------------------------
src/executor/reporter_json.py

from __future__ import annotations

import json
from pathlib import Path

from .artifacts import execution_dir, write_text
from .models import ExecutionReport


def write_report_json(run_dir: Path, report: ExecutionReport) -> Path:
    out = execution_dir(run_dir) / "report.json"
    write_text(out, json.dumps(report.to_dict(), indent=2))
    return out


-------------------------------------------------------------------------------------------------------------------------------
src/executor/reporter_pdf.py

from __future__ import annotations

from pathlib import Path
from typing import List

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from .artifacts import execution_dir
from .models import ExecutionReport


def _wrap(c: canvas.Canvas, text: str, x: float, y: float, max_width: float, line_height: float) -> float:
    """
    Very small wrap helper (keeps PDF simple + dependency-free).
    Returns new y after writing.
    """
    if not text:
        return y
    words = text.split()
    line = ""
    for w in words:
        nxt = (line + " " + w).strip()
        if c.stringWidth(nxt, "Helvetica", 10) <= max_width:
            line = nxt
        else:
            c.drawString(x, y, line)
            y -= line_height
            line = w
    if line:
        c.drawString(x, y, line)
        y -= line_height
    return y


def write_report_pdf(run_dir: Path, report: ExecutionReport) -> Path:
    out = execution_dir(run_dir) / "report.pdf"
    c = canvas.Canvas(str(out), pagesize=A4)
    width, height = A4

    margin = 0.6 * inch
    x = margin
    y = height - margin

    c.setFont("Helvetica-Bold", 16)
    c.drawString(x, y, "Execution Report")
    y -= 18

    c.setFont("Helvetica", 10)
    c.drawString(x, y, f"Run ID: {report.run_id}")
    y -= 14
    c.drawString(x, y, f"Base URL: {report.base_url_used}")
    y -= 14
    c.drawString(x, y, f"Started (UTC): {report.started_at_utc}")
    y -= 14
    c.drawString(x, y, f"Finished (UTC): {report.finished_at_utc}")
    y -= 18

    c.setFont("Helvetica-Bold", 12)
    c.drawString(x, y, "Summary")
    y -= 14

    c.setFont("Helvetica", 10)
    c.drawString(x, y, f"Total: {report.total}  Passed: {report.passed}  Failed: {report.failed}  Skipped: {report.skipped}")
    y -= 18

    c.setFont("Helvetica-Bold", 12)
    c.drawString(x, y, "Scenario Results")
    y -= 14

    # Table-ish listing
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x, y, "Status")
    c.drawString(x + 60, y, "Scenario")
    c.drawString(x + 360, y, "Duration(ms)")
    y -= 12
    c.line(x, y, width - margin, y)
    y -= 10

    c.setFont("Helvetica", 10)

    for r in report.results:
        if y < margin + 80:
            c.showPage()
            y = height - margin
            c.setFont("Helvetica-Bold", 12)
            c.drawString(x, y, "Scenario Results (cont.)")
            y -= 18
            c.setFont("Helvetica", 10)

        c.drawString(x, y, r.status.upper())
        c.drawString(x + 60, y, (r.scenario_name or "")[:45])
        c.drawString(x + 360, y, str(r.duration_ms))
        y -= 12

        if r.status == "failed":
            c.setFont("Helvetica", 9)
            err = f"{r.error_type or 'Error'}: {r.error_message or ''}"
            y = _wrap(c, err, x + 60, y, max_width=(width - margin - (x + 60)), line_height=11)
            if r.screenshot_path:
                y = _wrap(c, f"Screenshot: {r.screenshot_path}", x + 60, y, max_width=(width - margin - (x + 60)), line_height=11)
            y -= 4
            c.setFont("Helvetica", 10)

    c.showPage()
    c.save()
    return out
-------------------------------------------------------------------------------------------------------------------------

