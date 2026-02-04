from __future__ import annotations

import re
from pathlib import Path
from typing import List

from .models import Scenario, Step


def _clean_url(u: str) -> str:
    # Fix common LLM artifact: "amazon. com"
    return u.replace(" ", "").strip()


def load_scenarios_from_dir(gherkin_dir: Path) -> List[Scenario]:
    features = sorted(gherkin_dir.glob("*.feature"))
    scenarios: List[Scenario] = []

    for fp in features:
        text = fp.read_text(encoding="utf-8", errors="ignore")
        feature_name = "Feature"
        scenario_name = fp.stem
        base_url = "https://www.amazon.com"
        steps: List[Step] = []

        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue

            if line.lower().startswith("feature:"):
                feature_name = line.split(":", 1)[1].strip() or feature_name
                continue

            if line.lower().startswith("background:"):
                continue

            if line.lower().startswith("scenario:"):
                scenario_name = line.split(":", 1)[1].strip() or scenario_name
                continue

            # Steps
            for kw in ("Given", "When", "Then", "And"):
                if line.startswith(kw + " "):
                    step_text = line[len(kw) + 1 :].strip()

                    # Extract base url if present
                    if '"' in step_text and ("navigates to" in step_text.lower() or "goes to" in step_text.lower()):
                        parts = step_text.split('"')
                        if len(parts) >= 2 and parts[1].startswith("http"):
                            base_url = _clean_url(parts[1])

                    steps.append(Step(keyword=kw, text=step_text))
                    break

        scenarios.append(
            Scenario(
                feature_name=feature_name,
                scenario_name=scenario_name,
                base_url=base_url,
                steps=steps,
                feature_file=fp.name,
            )
        )

    return scenarios
