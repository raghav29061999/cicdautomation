from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from .models import ExecutionReport
from .artifacts import execution_dir


def write_report_pdf(run_dir: Path, report: ExecutionReport) -> Path:
    out_dir = execution_dir(run_dir)
    path = out_dir / "report.pdf"

    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4
    y = h - 48

    def line(txt: str, dy: int = 16):
        nonlocal y
        c.drawString(48, y, (txt or "")[:120])
        y -= dy
        if y < 72:
            c.showPage()
            y = h - 48

    d = report.to_dict()
    s = d.get("summary", {})

    line("Execution Report")
    line(f"Run ID: {d.get('run_id')}")
    line(f"Base URL: {d.get('base_url_used')}")
    line(f"Total: {s.get('total')}  Passed: {s.get('passed')}  Failed: {s.get('failed')}  Skipped: {s.get('skipped')}")
    line("-" * 100, dy=20)

    for r in d.get("results", []):
        line(f"[{r.get('status','')}] {r.get('scenario_name','')}")
        if r.get("error"):
            line(f"  {r['error']}")
        if r.get("screenshot_path"):
            line(f"  Screenshot: {r['screenshot_path']}")
        line("", dy=10)

    c.save()
    return path
