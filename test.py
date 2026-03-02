from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class DashboardKPI(BaseModel):
    title: str = Field(..., description="KPI label shown on dashboard card")
    value: Union[int, float, str] = Field(..., description="KPI value (number or text)")
    unit: Optional[str] = Field(default=None, description="Optional unit, e.g. %, INR, USD")
    note: Optional[str] = Field(default=None, description="Optional short note/explanation")


class DashboardChart(BaseModel):
    title: str = Field(..., description="Chart title")
    echarts: Dict[str, Any] = Field(..., description="Apache ECharts option JSON")
    note: Optional[str] = Field(default=None, description="Optional short note about the chart")


class DashboardResponse(BaseModel):
    table: str = Field(..., description="Selected table name, e.g. public.orders")
    session_id: Optional[str] = Field(default=None, description="Echo session id if provided")
    kpis: List[DashboardKPI] = Field(default_factory=list, description="Dashboard KPI cards")
    charts: List[DashboardChart] = Field(default_factory=list, description="Dashboard charts")
    notes: List[str] = Field(default_factory=list, description="Optional bullet insights for the dashboard")
    raw: Dict[str, Any] = Field(default_factory=dict, description="Optional debug metadata")


-------------------------------------------------------------------------------------------------------------

def init_api_dependencies(
    *,
    store: InMemoryEventStore,
    team: Team,
    insights_agent: Agent | None = None,
    dashboard_agent: Agent | None = None,
) -> None:
    global _STORE, _TEAM, _INSIGHTS_AGENT, _DASHBOARD_AGENT
    _STORE = store
    _TEAM = team

    if insights_agent is not None:
        _INSIGHTS_AGENT = insights_agent

    if dashboard_agent is not None:
        _DASHBOARD_AGENT = dashboard_agent


----------------------------------------------------------------------------------

def get_dashboard_agent() -> Agent:
    if _DASHBOARD_AGENT is None:
        raise RuntimeError("Dashboard agent dependency not initialized")
    return _DASHBOARD_AGENT
