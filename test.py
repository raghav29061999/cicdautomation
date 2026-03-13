class DashboardChart(BaseModel):
    title: str
    echarts: Dict[str, Any] | str
    note: Optional[str] = None


class DashboardTable(BaseModel):
    title: str
    markdown: str
    note: Optional[str] = None


class DashboardMetric(BaseModel):
    title: str
    value: int | float | str
    unit: Optional[str] = None
    note: Optional[str] = None


class DashboardResponse(BaseModel):
    table: str
    session_id: Optional[str] = None
    business_context: Optional[str] = None
    metrics: List[DashboardMetric] = Field(default_factory=list)
    charts: List[DashboardChart] = Field(default_factory=list)
    tables: List[DashboardTable] = Field(default_factory=list)
    column_descriptions: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)
    raw: Dict[str, Any] = Field(default_factory=dict)


------------------------------------

log_debug(
    f"DASHBOARD request_done request_id={request_id} session_id={sid} "
    f"table={table} business_context={response.get('business_context')} "
    f"metrics={len(response['metrics'])} charts={len(response['charts'])} "
    f"tables={len(response['tables'])}"
)
