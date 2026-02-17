from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Set

from src.api.orchestration.prompt_resolver import PromptResolver, ResolvedPrompt
from src.api.orchestration.agent_router import AgentRouter, RouteDecision
from src.api.orchestration.access_control import TableAccessController, AccessDecision


@dataclass(frozen=True)
class OrchestrationOutput:
    agent_name: str
    final_message_for_agent: str
    selected_table: Optional[str]
    route_reason: str


class Orchestrator:
    """
    Orchestration for Part 1:
      - Parse table from message
      - Enforce user access to that table
      - Select agent
      - Augment prompt with structured context (table binding)
    """

    def __init__(self, router: AgentRouter):
        self._resolver = PromptResolver()
        self._router = router

    def orchestrate(
        self,
        message: str,
        allowed_tables: Optional[Set[str]] = None,
    ) -> OrchestrationOutput:
        resolved: ResolvedPrompt = self._resolver.resolve(message)

        if not resolved.table:
            # No table chosen → agent can respond telling user to select a table
            decision: RouteDecision = self._router.route(table=None)
            return OrchestrationOutput(
                agent_name=decision.agent_name,
                final_message_for_agent=resolved.user_prompt,
                selected_table=None,
                route_reason=decision.reason,
            )

        acl = TableAccessController(allowed_tables=allowed_tables or set())
        access: AccessDecision = acl.can_access(resolved.table)
        if not access.allowed:
            # We do NOT change API schema; we just ensure the agent returns a clear refusal.
            decision = self._router.route(resolved.table)
            refusal = (
                f"You do not have access to table '{resolved.table}'. "
                f"Please choose a table you have access to."
            )
            return OrchestrationOutput(
                agent_name=decision.agent_name,
                final_message_for_agent=refusal,
                selected_table=resolved.table,
                route_reason=f"Denied: {access.reason}",
            )

        decision = self._router.route(resolved.table)

        # Provide structured context to agent (internal only)
        # This does NOT change /api/chat contract; it only changes what agents see.
        # Keep it concise and machine-readable.
        final_msg = (
            f"[CONTEXT]\n"
            f"selected_table={resolved.table}\n"
            f"[/CONTEXT]\n\n"
            f"{resolved.user_prompt}"
        )

        return OrchestrationOutput(
            agent_name=decision.agent_name,
            final_message_for_agent=final_msg,
            selected_table=resolved.table,
            route_reason=decision.reason,
        )
