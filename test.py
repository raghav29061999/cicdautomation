from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Tuple


_TABLE_PREFIX_RE = re.compile(
    r"^\s*table\s*=\s*([A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*)\s*\|\s*(.+)$",
    re.DOTALL,
)


@dataclass(frozen=True)
class ResolvedPrompt:
    table: Optional[str]
    user_prompt: str
    raw_message: str


class PromptResolver:
    """
    Resolves the UI contract:
      message := "table=<schema.table> | <user query>"
    """

    def resolve(self, message: str) -> ResolvedPrompt:
        raw = message or ""
        m = _TABLE_PREFIX_RE.match(raw)
        if not m:
            return ResolvedPrompt(table=None, user_prompt=raw.strip(), raw_message=raw)

        table = m.group(1).strip()
        user_prompt = m.group(2).strip()
        return ResolvedPrompt(table=table, user_prompt=user_prompt, raw_message=raw)
