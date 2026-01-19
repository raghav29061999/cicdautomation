"""
Phase 1 Orchestration Package

Responsibilities:
- Parse Phase-1 LLM output into structured artifacts
- Validate artifact presence and types
- Persist artifacts to runtime/runs/<run_id>/
- Provide a single-story "runner" entrypoint (LLM call later)
"""
-------------
from __future__ import annotations

from enum import Enum
from typing import Dict, Any, Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator


class OutputFormat(str, Enum):
    json_envelope = "json_envelope"
    strict_files = "strict_files"  # '### FILE:' blocks


REQUIRED_ARTIFACTS = (
    "RawUserStory.json",
    "AmbiguityReport.json",
    "CanonicalUserStoryCIR.json",
    "CoverageIntent.json",
    "RunManifest.json",
    "ContractDeltaSuggestions.md",
)


class ArtifactBundle(BaseModel):
    """
    Canonical in-memory representation of Phase-1 outputs (per story run).

    - run_id is the identifier for the run
    - artifacts maps filenames -> content
      - for .json artifacts, content is a dict (parsed JSON)
      - for .md artifacts, content is a string
    """
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(..., min_length=3)
    artifacts: Dict[str, Any] = Field(default_factory=dict)
    output_format: OutputFormat = Field(default=OutputFormat.json_envelope)

    @field_validator("artifacts")
    @classmethod
    def _validate_required_artifacts_present(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        missing = [k for k in REQUIRED_ARTIFACTS if k not in v]
        if missing:
            raise ValueError(f"Missing required artifacts: {missing}")
        return v

    def get_json(self, filename: str) -> Dict[str, Any]:
        val = self.artifacts.get(filename)
        if not isinstance(val, dict):
            raise TypeError(f"Artifact {filename} expected dict (JSON), got {type(val)}")
        return val

    def get_text(self, filename: str) -> str:
        val = self.artifacts.get(filename)
        if not isinstance(val, str):
            raise TypeError(f"Artifact {filename} expected str (text), got {type(val)}")
        return val


class ParseResult(BaseModel):
    """
    Parser return type that also includes light diagnostics.
    """
    model_config = ConfigDict(extra="forbid")

    bundle: ArtifactBundle
    warnings: Optional[list[str]] = Field(default_factory=list)
---------------------

from __future__ import annotations

import json
import re
from typing import Any, Dict, Tuple

from .models import ArtifactBundle, ParseResult, OutputFormat, REQUIRED_ARTIFACTS


_FILE_HEADER_RE = re.compile(r"^### FILE:\s*(?P<name>.+?)\s*$", re.MULTILINE)


def _strip_code_fences(text: str) -> str:
    """
    Strips one surrounding triple-backtick fence if present.
    Handles ```json ... ``` and ```markdown ... ```.
    """
    s = text.strip()
    if s.startswith("```"):
        # remove first line fence
        first_nl = s.find("\n")
        if first_nl == -1:
            return s
        s2 = s[first_nl + 1 :]
        # remove trailing fence
        if s2.strip().endswith("```"):
            s2 = s2.rsplit("```", 1)[0]
        return s2.strip()
    return s


def parse_phase1_output(text: str) -> ParseResult:
    """
    Parse Phase-1 output into an ArtifactBundle.

    Supports two formats:
    1) JSON envelope (recommended for prod):
       {"run_id": "...", "artifacts": {"RawUserStory.json": {...}, ..., "ContractDeltaSuggestions.md": "..."}}

    2) Strict file blocks (legacy/manual):
       ### FILE: RawUserStory.json
       ```json
       {...}
       ```
       ### FILE: ContractDeltaSuggestions.md
       ```markdown
       ...
       ```
    """
    s = text.strip()
    warnings: list[str] = []

    # Attempt JSON envelope first
    if s.startswith("{"):
        try:
            obj = json.loads(s)
            bundle = _parse_json_envelope(obj)
            return ParseResult(bundle=bundle, warnings=warnings)
        except Exception as e:
            warnings.append(f"JSON envelope parse failed; attempting strict file blocks. Reason: {e!r}")

    bundle = _parse_strict_file_blocks(s)
    return ParseResult(bundle=bundle, warnings=warnings)


def _parse_json_envelope(obj: Dict[str, Any]) -> ArtifactBundle:
    if "run_id" not in obj or "artifacts" not in obj:
        raise ValueError("JSON envelope missing required keys: run_id/artifacts")

    run_id = obj["run_id"]
    artifacts = obj["artifacts"]

    if not isinstance(artifacts, dict):
        raise TypeError("JSON envelope 'artifacts' must be an object/dict")

    # Validate required keys exist (ArtifactBundle validator also checks)
    for k in REQUIRED_ARTIFACTS:
        if k not in artifacts:
            raise ValueError(f"JSON envelope missing artifact: {k}")

    # Type normalization: ensure JSON artifacts are dict; md artifact is string
    normalized: Dict[str, Any] = {}
    for name, content in artifacts.items():
        if name.endswith(".json"):
            if not isinstance(content, dict):
                raise TypeError(f"{name} must be JSON object (dict), got {type(content)}")
            normalized[name] = content
        elif name.endswith(".md"):
            if not isinstance(content, str):
                raise TypeError(f"{name} must be markdown string, got {type(content)}")
            normalized[name] = content
        else:
            # allow extra files but keep them as-is
            normalized[name] = content

    return ArtifactBundle(run_id=run_id, artifacts=normalized, output_format=OutputFormat.json_envelope)


def _split_blocks(text: str) -> Dict[str, str]:
    """
    Splits `### FILE:` blocks into {filename: raw_block_content}.
    The raw content may include code fences.
    """
    matches = list(_FILE_HEADER_RE.finditer(text))
    if not matches:
        raise ValueError("No '### FILE:' headers found")

    blocks: Dict[str, str] = {}
    for idx, m in enumerate(matches):
        name = m.group("name").strip()
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        blocks[name] = content
    return blocks


def _parse_strict_file_blocks(text: str) -> ArtifactBundle:
    blocks = _split_blocks(text)

    # Ensure required artifacts exist
    missing = [k for k in REQUIRED_ARTIFACTS if k not in blocks]
    if missing:
        raise ValueError(f"Strict file blocks missing required artifacts: {missing}")

    # Parse each required artifact
    artifacts: Dict[str, Any] = {}
    run_id: str | None = None

    for filename, raw_block in blocks.items():
        content = _strip_code_fences(raw_block)

        if filename.endswith(".json"):
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in {filename}: {e}") from e
            artifacts[filename] = parsed

            # Extract run_id from first JSON that contains it
            if run_id is None and isinstance(parsed, dict) and "run_id" in parsed:
                run_id = str(parsed["run_id"])

        elif filename.endswith(".md"):
            artifacts[filename] = content
        else:
            # allow extra artifacts
            artifacts[filename] = content

    if not run_id:
        raise ValueError("Could not infer run_id from JSON artifacts (expected run_id field)")

    return ArtifactBundle(run_id=run_id, artifacts=artifacts, output_format=OutputFormat.strict_files)
---------------------

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .models import ArtifactBundle


def write_artifacts_to_run_dir(
    bundle: ArtifactBundle,
    runtime_root: str | Path,
    overwrite: bool = False,
) -> Path:
    """
    Persists artifacts to:
      <runtime_root>/runs/<run_id>/<filename>

    - JSON artifacts are written as pretty JSON (sorted keys for determinism)
    - Markdown artifacts are written as UTF-8 text
    """
    root = Path(runtime_root).expanduser().resolve()
    run_dir = root / "runs" / bundle.run_id

    if run_dir.exists() and not overwrite:
        raise FileExistsError(f"Run directory already exists: {run_dir} (set overwrite=True to replace)")

    run_dir.mkdir(parents=True, exist_ok=True)

    for filename, content in bundle.artifacts.items():
        out_path = run_dir / filename

        if filename.endswith(".json"):
            _write_json(out_path, content)
        else:
            _write_text(out_path, content)

    return run_dir


def _write_json(path: Path, content: Any) -> None:
    if not isinstance(content, (dict, list)):
        raise TypeError(f"Expected dict/list for JSON output {path.name}, got {type(content)}")

    text = json.dumps(content, indent=2, ensure_ascii=False, sort_keys=True)
    path.write_text(text + "\n", encoding="utf-8")


def _write_text(path: Path, content: Any) -> None:
    if not isinstance(content, str):
        # Be strict: markdown must be string
        raise TypeError(f"Expected str for text output {path.name}, got {type(content)}")
    path.write_text(content.strip() + "\n", encoding="utf-8")
---------------

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
import os

from ingestion.story_loader import UserStory
from .parser import parse_phase1_output
from .writer import write_artifacts_to_run_dir
from .models import ArtifactBundle


@dataclass(frozen=True)
class Phase1RunConfig:
    """
    Configuration for Phase-1 runtime artifact generation.

    NOTE: LLM invocation is intentionally not implemented yet.
    This runner supports:
    - reading a story
    - accepting a raw LLM response string (manual paste during development)
    - parsing
    - writing artifacts to runtime dir
    """
    runtime_root: str = "./runtime"
    overwrite: bool = False


def run_phase1_from_llm_output(
    story: UserStory,
    llm_output_text: str,
    config: Phase1RunConfig = Phase1RunConfig(),
) -> Path:
    """
    Development helper:
    - You run the prompt manually in an LLM UI
    - Paste the output here
    - This function parses and writes per-run artifacts

    Later, replace llm_output_text with a real LLM call.
    """
    parse_result = parse_phase1_output(llm_output_text)
    bundle: ArtifactBundle = parse_result.bundle

    # Optional guard: ensure story title aligns (soft check)
    # We do NOT fail hard here because naming conventions vary.
    # You can harden this later using story_id/story_name matching rules.

    run_dir = write_artifacts_to_run_dir(
        bundle=bundle,
        runtime_root=config.runtime_root,
        overwrite=config.overwrite,
    )
    return run_dir


if __name__ == "__main__":
    # Manual workflow test:
    # 1) Put story text in user_story/<name>.txt
    # 2) Run this script
    # 3) Paste LLM output when prompted (or redirect from file)
    load_dotenv()
    story_dir = os.getenv("USER_STORY_DIR", "./user_story")
    runtime_root = os.getenv("RUNTIME_ROOT", "./runtime")

    # Pick one story file deterministically
    from ingestion.story_loader import load_user_stories
    stories = load_user_stories(story_dir)
    if not stories:
        raise SystemExit(f"No stories found in {story_dir}")

    story = stories[0]
    print(f"Selected story: {story.filename}")
    print("Paste the LLM output now (end with CTRL+D on mac/linux or CTRL+Z then Enter on windows):")

    import sys
    llm_output = sys.stdin.read()

    run_dir = run_phase1_from_llm_output(
        story=story,
        llm_output_text=llm_output,
        config=Phase1RunConfig(runtime_root=runtime_root, overwrite=False),
    )
    print(f"Wrote artifacts to: {run_dir}")
