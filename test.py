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

    # ensure execution folder exists
    _ = execution_dir(run_dir)

    results: List[ScenarioResult] = []
    passed = failed = skipped = 0

    base_used = cfg.base_url_override or (scenarios[0].base_url if scenarios else "BASE_URL")

    for sc in scenarios:
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

    write_report_json(run_dir, report)
    write_report_pdf(run_dir, report)
    return report
