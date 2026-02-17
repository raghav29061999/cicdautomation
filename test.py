from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class RouteDecision:
    agent_name: str
    reason: str


class AgentRouter:
    """
    Table-aware routing.

    Use a config-driven mapping. You can replace this with DB-driven routing later.
    """

    def __init__(self, table_prefix_to_agent: Optional[Dict[str, str]] = None, default_agent: str = "agent_1"):
        self._map = table_prefix_to_agent or {}
        self._default = default_agent

    def route(self, table: Optional[str]) -> RouteDecision:
        if not table:
            return RouteDecision(agent_name=self._default, reason="No table selected; default routing")

        # Example: map by schema prefix or naming conventions:
        # table="public.orders" => name="orders"
        _, name = table.split(".", 1)

        for prefix, agent in self._map.items():
            if name.startswith(prefix):
                return RouteDecision(agent_name=agent, reason=f"Table name starts with '{prefix}'")

        return RouteDecision(agent_name=self._default, reason="No mapping match; default routing")











------------------------------------------------------------------------------






from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Set, Optional


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    reason: str


class TableAccessController:
    """
    Enforces that the user can only query tables they are allowed to.

    Plug this into your real auth/session model. For now, it accepts a set[str]
    of allowed tables (e.g., from request.state.user, or your store).
    """

    def __init__(self, allowed_tables: Optional[Iterable[str]] = None):
        self.allowed_tables: Set[str] = set(t.strip() for t in (allowed_tables or []) if t and t.strip())

    def can_access(self, table: str) -> AccessDecision:
        if not table:
            return AccessDecision(allowed=False, reason="No table provided")
        if not self.allowed_tables:
            # If you want to *require* ACLs, flip this to deny by default.
            return AccessDecision(allowed=True, reason="No ACL list configured; allowing by default")
        if table in self.allowed_tables:
            return AccessDecision(allowed=True, reason="Table is in user's allowed set")
        return AccessDecision(allowed=False, reason="Table is not in user's allowed set")

