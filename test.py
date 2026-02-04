
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Step:
    keyword: str  # Given/When/Then/And
    text: str


@dataclass
class Scenario:
    feature_name: str
    scenario_name: str
    base_url: str
    steps: List[Step]
    feature_file: str  # file name


@dataclass
class ScenarioResult:
    feature_file: str
    scenario_name: str
    status: str  # passed|failed|skipped
    error: Optional[str] = None
    duration_ms: Optional[int] = None
    screenshot_path: Optional[str] = None


@dataclass
class ExecutionReport:
    run_id: str
    run_dir: str
    started_at_utc: str
    finished_at_utc: str
    base_url_used: str

    total: int
    passed: int
    failed: int
    skipped: int

    results: List[ScenarioResult]

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "run_dir": self.run_dir,
            "started_at_utc": self.started_at_utc,
            "finished_at_utc": self.finished_at_utc,
            "base_url_used": self.base_url_used,
            "summary": {
                "total": self.total,
                "passed": self.passed,
                "failed": self.failed,
                "skipped": self.skipped,
            },
            "results": [r.__dict__ for r in self.results],
        }
