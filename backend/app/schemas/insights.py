from typing import Any, Literal

from pydantic import BaseModel, Field

InsightMode = Literal["answer", "chart", "table", "report"]
InsightPlannerSource = Literal["deterministic", "deterministic_followup", "anthropic_structured", "claude_fallback"]
InsightChatMessageRole = Literal["user", "assistant", "system", "tool"]
InsightArtifactType = Literal["csv", "diagram", "brief"]
InsightTool = Literal[
    "context.globalSummary",
    "spend.summary",
    "spend.groupBy",
    "spend.compare",
    "spend.topMerchants",
    "spend.topTransactions",
    "spend.sqlQuery",
    "review.currentQueue",
    "policy.latestFindings",
    "risk.latestSignals",
    "report.generate",
    "report.exportCsv",
    "policy.retrieveClauses",
]


class InsightPlan(BaseModel):
    intent: str
    mode: InsightMode = "answer"
    tool: InsightTool = "spend.summary"
    filters: dict[str, Any] = Field(default_factory=dict)
    group_by: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=lambda: ["sum_amount_cad", "transaction_count"])
    sort: list[dict[str, Any]] = Field(default_factory=list)
    limit: int = 100
    visualization: str | None = None
    sql_statement: str | None = None
    context_options: dict[str, Any] = Field(default_factory=dict)
    comparison_options: dict[str, Any] = Field(default_factory=dict)
    report_options: dict[str, Any] = Field(default_factory=dict)


class InsightValidationResult(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class InsightPlanRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    mode: InsightMode | None = None


class InsightPageContext(BaseModel):
    page: str | None = Field(default=None, max_length=200)
    route: str | None = Field(default=None, max_length=500)
    payload: dict[str, Any] = Field(default_factory=dict)


class AskContextEntity(BaseModel):
    type: str
    id: str | None = None
    label: str
    status: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class AskContextArtifact(BaseModel):
    type: str
    id: str | None = None
    label: str
    status: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AskContextEnvelope(BaseModel):
    page_context: InsightPageContext | None = None
    focus_entities: list[AskContextEntity] = Field(default_factory=list)
    visible_entities: list[AskContextEntity] = Field(default_factory=list)
    artifacts: list[AskContextArtifact] = Field(default_factory=list)
    global_summaries: dict[str, Any] = Field(default_factory=dict)
    hydrated_entities: dict[str, Any] = Field(default_factory=dict)
    recent_results: list[dict[str, Any]] = Field(default_factory=list)
    recent_artifacts: list[AskContextArtifact] = Field(default_factory=list)
    context_scope: list[str] = Field(default_factory=list)


class InsightPlanResponse(BaseModel):
    question: str
    plan: InsightPlan
    validation: InsightValidationResult
    critic: InsightValidationResult
    planner_source: InsightPlannerSource = "deterministic"


class InsightQueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    mode: InsightMode | None = None
    session_id: str | None = None
    page_context: InsightPageContext | None = None


class InsightCitation(BaseModel):
    rule_code: str | None = None
    clause_id: str | None = None
    title: str | None = None
    text: str
    source: str | None = None
    match_score: float | None = None


class InsightChatMessage(BaseModel):
    id: str | None = None
    session_id: str | None = None
    role: InsightChatMessageRole
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None


class InsightSession(BaseModel):
    id: str
    title: str
    created_by_employee_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class InsightSessionCreateRequest(BaseModel):
    title: str | None = None
    initial_question: str | None = Field(default=None, max_length=2000)
    page_context: InsightPageContext | None = None


class InsightSessionDetail(BaseModel):
    session: InsightSession
    messages: list[InsightChatMessage] = Field(default_factory=list)


class InsightResultRow(BaseModel):
    label: str
    values: dict[str, Any] = Field(default_factory=dict)


class InsightQueryResponse(BaseModel):
    question: str
    session_id: str | None = None
    plan: InsightPlan
    validation: InsightValidationResult
    planner_source: InsightPlannerSource = "deterministic"
    summary: str
    columns: list[str] = Field(default_factory=list)
    rows: list[InsightResultRow] = Field(default_factory=list)
    citations: list[InsightCitation] = Field(default_factory=list)
    visualization: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class InsightArtifactRequest(BaseModel):
    result: InsightQueryResponse
