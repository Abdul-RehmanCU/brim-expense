from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Any, Literal

from anthropic import Anthropic
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.config import get_settings
from app.database.supabase_client import get_supabase_client
from app.schemas.insights import (
    AskContextEnvelope,
    InsightChatMessage,
    InsightCitation,
    InsightPageContext,
    InsightPlan,
    InsightPlanRequest,
    InsightPlanResponse,
    InsightQueryRequest,
    InsightQueryResponse,
    InsightSession,
    InsightSessionCreateRequest,
    InsightSessionDetail,
    InsightValidationResult,
)
from app.services import ask_context_service, sql_query_service
from app.tools.spend_tools import execute_insight_tool
from app.services.ai_service import default_insight_response_client, parse_strict_json

ALLOWED_TOOLS = {
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
}
ALLOWED_MODES = {"answer", "chart", "table", "report"}
ALLOWED_METRICS = {
    "sum_amount_cad",
    "amount_cad",
    "transaction_count",
    "avg_amount_cad",
    "policy_flag_count",
    "risk_flag_count",
    "missing_receipt_count",
    "missing_preapproval_count",
}
ALLOWED_DIMENSIONS = {
    "department",
    "employee",
    "merchant",
    "business_category",
    "normalized_category",
    "month",
    "policy_status",
    "risk_level",
}
ALLOWED_FILTERS = {
    "date_start",
    "date_end",
    "department",
    "employee",
    "merchant",
    "category",
    "queue_status",
    "policy_status",
    "review_level",
    "risk_level",
    "debit_credit",
    "transaction_ids",
}
BLOCKED_KEYS = {"sql", "raw_sql", "query_sql", "statement"}
KNOWN_DEPARTMENTS = (
    "Marketing",
    "Engineering",
    "Sales",
    "Operations",
    "Finance",
    "HR",
    "Customer Success",
    "Executive",
)
FOLLOW_UP_HINTS = (" now ", " only ", " just ", " those", " that ", " same ", " what about ", " narrow ", " filter ")
REVIEW_QUEUE_TERMS = ("review queue", "flagged", "critical", "review item", "triage", "needs review")
CHART_REQUEST_TERMS = (" chart ", " graph ", " plot ", " visualize ", " visualise ")
TIME_SERIES_TERMS = (" by month ", " over time ", " trend ", " monthly ", " month by month ")
TOP_TRANSACTION_TERMS = (
    " most expensive ",
    " highest amount ",
    " highest amounts ",
    " largest expense ",
    " largest expenses ",
    " largest amount ",
    " top expenses ",
    " expensive amounts ",
)
TABLE_REFERENCE_TERMS = (" this table ", " this list ", " visible table ", " on this table ", " in this table ")
PAGE_EXPLANATION_TERMS = (
    "what am i looking at",
    "what am i seeing",
    "what is this page",
    "what does this page show",
    "what is this screen",
    "what am i looking at here",
    "explain this page",
    "explain this screen",
    "what is going on here",
)
POLICY_RETRIEVAL_TERMS = (
    "clause",
    "receipt",
    "preapproval",
    "pre-approval",
    "reimburs",
    "why was",
    "why is",
    "cite",
    "citation",
    "source",
)
CONTEXT_FILTER_ALIAS_MAP = {
    "date_start": ("date_start", "start_date", "period_start"),
    "date_end": ("date_end", "end_date", "period_end"),
    "department": ("department", "department_name"),
    "employee": ("employee", "employee_name"),
    "merchant": ("merchant", "merchant_name", "normalized_merchant_name"),
    "category": ("category", "business_category", "normalized_category"),
    "queue_status": ("queue_status",),
    "policy_status": ("policy_status",),
    "review_level": ("review_level", "severity", "severity_filter"),
    "risk_level": ("risk_level",),
    "debit_credit": ("debit_credit",),
    "transaction_ids": ("transaction_ids", "visible_transaction_ids"),
}


class StructuredSortSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    direction: Literal["asc", "desc"] = "desc"


class StructuredInsightPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: str
    mode: Literal["answer", "chart", "table", "report"] = "answer"
    tool: Literal[
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
        "policy.retrieveClauses",
    ] = "spend.summary"
    filters: dict[str, Any] = Field(default_factory=dict)
    group_by: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    sort: list[StructuredSortSpec] = Field(default_factory=list)
    limit: int = 100
    visualization: str | None = None
    sql_statement: str | None = None
    context_options: dict[str, Any] = Field(default_factory=dict)
    comparison_options: dict[str, Any] = Field(default_factory=dict)
    report_options: dict[str, Any] = Field(default_factory=dict)


class AnthropicInsightPlannerClient:
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for Anthropic insight planning.")
        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.resolved_anthropic_insights_model

    def create_plan(
        self,
        *,
        question: str,
        mode: str | None,
        history: list[InsightChatMessage],
        last_plan: InsightPlan | None,
        page_context: InsightPageContext | None,
        ask_context: AskContextEnvelope | None,
    ) -> InsightPlan:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=1200,
            temperature=0,
            system=(
                "You are a guarded planner for an expense analytics assistant. "
                "Return strict JSON only with no markdown fences or prose. "
                "Select only from approved tools, dimensions, metrics, and filters. "
                "Use conversation history to resolve follow-up questions. "
                "You may use spend.sqlQuery only when the request cannot be expressed cleanly with the safer structured spend tools. "
                "When you use spend.sqlQuery, provide a single read-only PostgreSQL SELECT or WITH query in sql_statement. "
                "Never emit mutating, administrative, multi-statement, commented, or privileged SQL. "
                "Use policy.retrieveClauses when the user is asking what policy says, why a policy rule exists, "
                "or asks for a citation or clause explanation."
            ),
            messages=[
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "question": question,
                            "requested_mode": mode,
                            "history": [message.model_dump(mode="json") for message in history[-8:]],
                            "last_plan": last_plan.model_dump(mode="json") if last_plan else None,
                            "page_context": page_context.model_dump(mode="json") if page_context else None,
                            "ask_context": ask_context.model_dump(mode="json") if ask_context else None,
                            "allowed_tools": sorted(ALLOWED_TOOLS),
                            "allowed_modes": sorted(ALLOWED_MODES),
                            "allowed_metrics": sorted(ALLOWED_METRICS),
                            "allowed_dimensions": sorted(ALLOWED_DIMENSIONS),
                            "allowed_filters": sorted(ALLOWED_FILTERS),
                            "known_departments": list(KNOWN_DEPARTMENTS),
                            "sql_schema_context": sql_query_service.allowed_sql_schema_context(),
                            "instructions": [
                                "Prefer spend.compare when the question compares two departments.",
                                "Prefer context.globalSummary when the user asks about overall app status, reports, approvals, policy setup, or cross-page summaries.",
                                "Prefer spend.groupBy for grouped spend analysis.",
                                "Prefer spend.topTransactions when the user asks for the biggest, most expensive, or top transaction rows.",
                                "Use spend.sqlQuery for flexible read-only analysis that needs richer joins, aliases, or custom aggregation than the structured tools can express.",
                                "Prefer policy.latestFindings for aggregated policy questions.",
                                "Prefer risk.latestSignals for transaction-level risk questions.",
                                "Prefer policy.retrieveClauses for policy explanation or citation questions.",
                                "For follow-up questions like 'now only Marketing', preserve the prior analytical intent and update filters.",
                                "Use page_context.details when the user refers to this table, the visible rows, or the current page.",
                                "Do not emit report.generate or report.exportCsv for ordinary Talk to Data questions.",
                            ],
                            "required_output_shape": {
                                "intent": "string",
                                "mode": "answer|chart|table|report",
                                "tool": "approved tool name",
                                "filters": {},
                                "group_by": [],
                                "metrics": [],
                                "sort": [{"field": "approved metric or dimension", "direction": "asc|desc"}],
                                "limit": 100,
                                "visualization": "string or null",
                                "sql_statement": "string or null",
                                "context_options": {},
                                "comparison_options": {},
                                "report_options": {},
                            },
                        },
                        ensure_ascii=True,
                    ),
                }
            ],
        )
        text = "".join(
            block.text if hasattr(block, "text") else str(getattr(block, "content", ""))
            for block in response.content
        )
        payload = parse_strict_json(text)
        parsed = StructuredInsightPlan(**payload)
        return InsightPlan(**parsed.model_dump(mode="json"))


def create_insight_session(request: InsightSessionCreateRequest | None = None) -> InsightSession:
    request = request or InsightSessionCreateRequest()
    page_context = getattr(request, "page_context", None)
    title_source = ((getattr(request, "title", None) or getattr(request, "initial_question", None) or "Talk to Data")).strip()
    title = title_source[:120] or "Talk to Data"
    rows = (
        get_supabase_client()
        .table("chat_sessions")
        .insert({"title": title})
        .execute()
        .data
        or []
    )
    if not rows:
        raise HTTPException(status_code=500, detail="Could not create insight session.")
    session = _session_from_row(rows[0])
    if page_context:
        _persist_session_context(session.id, page_context)
    return session


def list_insight_sessions(limit: int = 40) -> list[InsightSession]:
    rows = (
        get_supabase_client()
        .table("chat_sessions")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )
    return [_session_from_row(row) for row in rows]


def get_insight_session(session_id: str) -> InsightSessionDetail:
    session = _fetch_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Insight session was not found.")
    return InsightSessionDetail(session=session, messages=_load_session_messages(session_id, include_context_messages=False))


def create_insight_plan(
    request: InsightPlanRequest,
    session_messages: list[InsightChatMessage] | None = None,
    page_context: InsightPageContext | None = None,
    ask_context: AskContextEnvelope | None = None,
) -> InsightPlanResponse:
    history = session_messages or []
    resolved_page_context = page_context or _extract_latest_page_context(history)
    last_plan = _extract_last_assistant_plan(history)
    last_analysis_frame = _extract_last_analysis_frame(history)
    followup_plan = maybe_apply_followup_plan(request.question, request.mode, last_plan, last_analysis_frame)
    page_context_plan = maybe_create_page_context_plan(request.question, request.mode, resolved_page_context)
    if followup_plan:
        plan = apply_page_context_to_plan(followup_plan, resolved_page_context)
        planner_source = "deterministic_followup"
    elif page_context_plan:
        plan = apply_page_context_to_plan(page_context_plan, resolved_page_context)
        planner_source = "deterministic"
    else:
        base_plan = apply_page_context_to_plan(
            deterministic_plan(
                request.question,
                request.mode,
                last_plan=last_plan,
                last_analysis_frame=last_analysis_frame,
            ),
            resolved_page_context,
        )
        plan = base_plan
        planner_source = "deterministic"
        if _should_try_ai_plan(request.question, plan, history):
            try:
                ai_plan = AnthropicInsightPlannerClient().create_plan(
                    question=request.question,
                    mode=request.mode,
                    history=history,
                    last_plan=last_plan,
                    page_context=resolved_page_context,
                    ask_context=ask_context,
                )
                ai_plan = apply_page_context_to_plan(ai_plan, resolved_page_context)
                if validate_plan(ai_plan).valid:
                    plan = ai_plan
                    planner_source = "anthropic_structured"
                else:
                    plan = base_plan
                    planner_source = "deterministic"
            except Exception:
                planner_source = "deterministic"

    critic = critic_validate_plan(request.question, plan)
    validation = validate_plan(plan)
    return InsightPlanResponse(
        question=request.question,
        plan=plan,
        critic=critic,
        validation=validation,
        planner_source=planner_source,
    )


def query_insights(request: InsightQueryRequest) -> InsightQueryResponse:
    page_context = getattr(request, "page_context", None)
    session = _ensure_session(request.session_id, request.question, page_context)
    _persist_session_context(session.id, page_context)
    history = _load_session_messages(session.id, include_context_messages=True)
    resolved_page_context = page_context or _extract_latest_page_context(history)
    ask_context = ask_context_service.build_ask_context_envelope(
        page_context=resolved_page_context,
        history=history,
    )
    plan_response = create_insight_plan(
        InsightPlanRequest(question=request.question, mode=request.mode),
        session_messages=history,
        page_context=resolved_page_context,
        ask_context=ask_context,
    )
    if not plan_response.critic.valid:
        blocked = _blocked_response(request.question, plan_response.plan, plan_response.critic, session.id)
        _persist_query_exchange(session.id, request.question, blocked, page_context=resolved_page_context)
        return blocked
    if not plan_response.validation.valid:
        blocked = _blocked_response(request.question, plan_response.plan, plan_response.validation, session.id)
        _persist_query_exchange(session.id, request.question, blocked, page_context=resolved_page_context)
        return blocked

    if plan_response.plan.tool == "context.globalSummary":
        rows, metadata, citations = ask_context_service.execute_context_summary_tool(
            plan_response.plan,
            ask_context,
            request.question,
        )
    elif plan_response.plan.tool == "spend.sqlQuery":
        prepared_sql, sql_metadata = sql_query_service.validate_and_prepare_sql(
            question=request.question,
            sql_statement=plan_response.plan.sql_statement or "",
            page_context=resolved_page_context,
            ask_context=ask_context.model_dump(mode="json"),
            limit=plan_response.plan.limit,
        )
        rows, metadata = sql_query_service.execute_read_only_sql(prepared_sql, plan_response.plan.limit)
        citations = []
        metadata = {**metadata, **sql_metadata}
    else:
        rows, metadata, citations = execute_insight_tool(plan_response.plan, question=request.question, history=history)
    analysis_frame = build_analysis_frame(
        question=request.question,
        plan=plan_response.plan,
        rows=rows,
        page_context=resolved_page_context,
    )
    response_metadata = metadata_with_context(
        metadata,
        resolved_page_context,
        ask_context,
        plan_response.plan,
        citations,
        analysis_frame,
    )
    fallback_summary = summarize_result(plan_response.plan, rows, metadata, citations)
    response = InsightQueryResponse(
        question=request.question,
        session_id=session.id,
        plan=plan_response.plan,
        validation=plan_response.validation,
        planner_source=plan_response.planner_source,
        summary=compose_insight_response(
            question=request.question,
            plan=plan_response.plan,
            rows=rows,
            metadata=response_metadata,
            citations=citations,
            page_context=resolved_page_context,
            ask_context=ask_context,
            history=history,
            fallback_summary=fallback_summary,
        ),
        columns=infer_columns(rows),
        rows=rows,
        citations=citations,
        visualization=plan_response.plan.visualization,
        metadata=response_metadata,
    )
    _persist_query_exchange(session.id, request.question, response, page_context=resolved_page_context)
    return response


def deterministic_plan(
    question: str,
    mode: str | None = None,
    last_plan: InsightPlan | None = None,
    last_analysis_frame: dict[str, Any] | None = None,
) -> InsightPlan:
    normalized = f" {question.lower().strip()} "
    chart_requested = _wants_chart(normalized)
    requested_mode = mode or ("chart" if chart_requested else "answer")
    mentioned_departments = extract_departments(normalized)
    comparison_requested = wants_comparison(normalized)
    category_breakdown_requested = "category" in normalized
    period_filters = extract_relative_date_filters(normalized)
    time_series_requested = _wants_time_series(normalized) or (chart_requested and bool(period_filters))
    global_context_plan = maybe_create_global_context_plan(normalized, requested_mode)

    if global_context_plan:
        return global_context_plan

    if _wants_review_queue(normalized):
        review_level = "critical" if "critical" in normalized else None
        queue_status = None if "all" in normalized else "open"
        if "resolved" in normalized:
            queue_status = "resolved"
        elif "approval" in normalized:
            queue_status = "in_approval"
        return InsightPlan(
            intent="review_queue_summary" if _is_review_summary_question(normalized) else "review_queue_items",
            mode="table" if requested_mode == "answer" else requested_mode,
            tool="review.currentQueue",
            filters={
                key: value
                for key, value in {
                    "queue_status": queue_status,
                    "review_level": review_level,
                }.items()
                if value not in (None, "", [])
            },
            metrics=["sum_amount_cad", "transaction_count", "policy_flag_count", "risk_flag_count"],
            sort=[{"field": "review_priority", "direction": "desc"}],
            limit=_extract_requested_limit(normalized, default=10),
            visualization="table",
        )

    if _is_policy_retrieval_question(normalized, last_plan):
        return InsightPlan(
            intent="policy_clause_lookup",
            mode="answer",
            tool="policy.retrieveClauses",
            limit=5,
            visualization="table",
        )

    if (last_plan or last_analysis_frame) and _is_department_spend_followup(normalized, last_plan, last_analysis_frame):
        return _build_department_spend_followup_plan(
            normalized,
            requested_mode,
            mentioned_departments,
            chart_requested=chart_requested,
        )

    if comparison_requested and len(mentioned_departments) >= 2:
        comparison_targets = mentioned_departments[:2]
        focus_dimension = "month" if time_series_requested else "business_category" if category_breakdown_requested else "department"
        return InsightPlan(
            intent="department_spend_comparison",
            mode="chart" if time_series_requested or chart_requested else "table" if requested_mode == "answer" else requested_mode,
            tool="spend.compare",
            filters={"department": comparison_targets, **period_filters},
            group_by=[focus_dimension],
            metrics=["sum_amount_cad", "transaction_count", "avg_amount_cad"],
            visualization="line" if focus_dimension == "month" else "bar",
            comparison_options={
                "dimension": "department",
                "targets": comparison_targets,
                "focus_dimension": focus_dimension,
            },
        )

    if mentioned_departments and period_filters:
        department_filter = mentioned_departments if len(mentioned_departments) > 1 else mentioned_departments[0]
        if time_series_requested:
            return InsightPlan(
                intent="department_spend_trend",
                mode="chart",
                tool="spend.groupBy",
                filters={"department": department_filter, **period_filters},
                group_by=["month"],
                metrics=["sum_amount_cad", "transaction_count", "avg_amount_cad"],
                sort=[{"field": "month", "direction": "asc"}],
                limit=24,
                visualization="line",
            )
        return InsightPlan(
            intent="department_spend_summary",
            mode=requested_mode,
            tool="spend.summary",
            filters={"department": department_filter, **period_filters},
            metrics=["sum_amount_cad", "transaction_count", "avg_amount_cad"],
            sort=[{"field": "sum_amount_cad", "direction": "desc"}],
            visualization="metric",
        )

    if "marketing" in normalized and "category" in normalized:
        return InsightPlan(
            intent="marketing_spend_by_category",
            mode="chart" if requested_mode == "answer" else requested_mode,
            tool="spend.groupBy",
            filters={"department": "Marketing"},
            group_by=["business_category"],
            metrics=["sum_amount_cad", "transaction_count", "avg_amount_cad"],
            sort=[{"field": "sum_amount_cad", "direction": "desc"}],
            limit=100,
            visualization="bar",
        )

    if " compare " in normalized and " engineering " in normalized and " sales " in normalized:
        return InsightPlan(
            intent="compare_engineering_vs_sales",
            mode="chart" if requested_mode == "answer" else requested_mode,
            tool="spend.compare",
            filters={"department": ["Engineering", "Sales"]},
            group_by=["department"],
            metrics=["sum_amount_cad", "transaction_count", "avg_amount_cad"],
            visualization="bar",
            comparison_options={
                "dimension": "department",
                "targets": ["Engineering", "Sales"],
                "focus_dimension": "department",
            },
        )

    if " top " in normalized and (" merchant " in normalized or " merchants " in normalized or " vendor " in normalized):
        return InsightPlan(
            intent="top_merchants",
            mode="table" if requested_mode == "answer" else requested_mode,
            tool="spend.topMerchants",
            group_by=["merchant"],
            metrics=["sum_amount_cad", "transaction_count", "avg_amount_cad"],
            sort=[{"field": "sum_amount_cad", "direction": "desc"}],
            limit=10,
            visualization="table",
        )

    if _wants_top_transactions(normalized):
        requested_limit = _extract_requested_limit(normalized, default=10)
        return InsightPlan(
            intent="top_transactions",
            mode="chart" if chart_requested else "table" if requested_mode == "answer" else requested_mode,
            tool="spend.topTransactions",
            filters=period_filters,
            metrics=["sum_amount_cad", "transaction_count", "avg_amount_cad"],
            sort=[{"field": "amount_cad", "direction": "desc"}],
            limit=requested_limit,
            visualization="bar" if chart_requested else "table",
        )

    if period_filters and time_series_requested:
        return InsightPlan(
            intent="spend_trend",
            mode="chart",
            tool="spend.groupBy",
            filters=period_filters,
            group_by=["month"],
            metrics=["sum_amount_cad", "transaction_count", "avg_amount_cad"],
            sort=[{"field": "month", "direction": "asc"}],
            limit=24,
            visualization="line",
        )

    if ("high-risk" in normalized or "high risk" in normalized or " risk " in normalized) and " transaction" in normalized:
        return InsightPlan(
            intent="high_risk_transactions",
            mode="table" if requested_mode == "answer" else requested_mode,
            tool="risk.latestSignals",
            filters={"risk_level": ["medium", "high", "critical"]},
            metrics=["sum_amount_cad", "transaction_count", "risk_flag_count"],
            sort=[{"field": "risk_score", "direction": "desc"}],
            limit=100,
            visualization="table",
        )

    if ("policy" in normalized or "compliance" in normalized or "flag" in normalized) and "department" in normalized:
        return InsightPlan(
            intent="policy_flags_by_department",
            mode="chart" if requested_mode == "answer" else requested_mode,
            tool="policy.latestFindings",
            group_by=["department"],
            metrics=["policy_flag_count", "sum_amount_cad", "transaction_count"],
            sort=[{"field": "policy_flag_count", "direction": "desc"}],
            limit=100,
            visualization="bar",
        )

    return InsightPlan(
        intent="spend_summary",
        mode=requested_mode,
        tool="spend.summary",
        filters=period_filters,
        metrics=["sum_amount_cad", "transaction_count", "avg_amount_cad"],
        sort=[{"field": "sum_amount_cad", "direction": "desc"}],
        visualization="bar" if chart_requested else "metric",
    )


def maybe_apply_followup_plan(
    question: str,
    mode: str | None,
    last_plan: InsightPlan | None,
    last_analysis_frame: dict[str, Any] | None = None,
) -> InsightPlan | None:
    if not last_plan:
        return None
    normalized = f" {question.lower().strip()} "
    chart_requested = _wants_chart(normalized)
    if (
        not any(hint in normalized for hint in FOLLOW_UP_HINTS)
        and not _wants_review_queue(normalized)
        and not _looks_like_contextual_followup(normalized, last_analysis_frame)
        and len(question.split()) > 6
    ):
        return None

    if _is_department_spend_followup(normalized, last_plan, last_analysis_frame):
        return _build_department_spend_followup_plan(
            normalized,
            mode or ("chart" if chart_requested else last_plan.mode),
            extract_departments(normalized),
            chart_requested=chart_requested,
        )

    plan = last_plan.model_copy(deep=True)
    plan.mode = mode or ("chart" if chart_requested else plan.mode)
    if last_plan.tool == "context.globalSummary":
        followup_context_plan = maybe_create_global_context_plan(normalized, plan.mode)
        if followup_context_plan:
            return followup_context_plan
    if last_plan.tool == "review.currentQueue":
        plan.tool = "review.currentQueue"
        plan.intent = "review_queue_explanation" if _wants_review_explanation(normalized) else "review_queue_items"
        plan.mode = "table" if plan.mode == "answer" else plan.mode
        if "critical" in normalized:
            plan.filters["review_level"] = "critical"
        if "resolved" in normalized:
            plan.filters["queue_status"] = "resolved"
        elif "approval" in normalized:
            plan.filters["queue_status"] = "in_approval"
        elif "open" in normalized or "flagged" in normalized or "queue" in normalized:
            plan.filters["queue_status"] = "open"
        if "all" in normalized:
            plan.filters.pop("queue_status", None)
        requested_limit = _extract_requested_limit(normalized, default=plan.limit)
        plan.limit = requested_limit
    mentioned_departments = extract_departments(normalized)
    if mentioned_departments:
        plan.filters["department"] = mentioned_departments if len(mentioned_departments) > 1 else mentioned_departments[0]
    if "category" in normalized and "business_category" not in plan.group_by:
        plan.group_by = ["business_category"]
        plan.visualization = "bar"
    if "merchant" in normalized:
        plan.intent = "top_merchants"
        plan.tool = "spend.topMerchants"
        plan.mode = "table"
        plan.group_by = ["merchant"]
        plan.metrics = ["sum_amount_cad", "transaction_count", "avg_amount_cad"]
        plan.visualization = "table"
    if chart_requested and plan.tool == "spend.summary":
        plan.intent = "spend_trend"
        plan.tool = "spend.groupBy"
        plan.mode = "chart"
        plan.group_by = ["month"]
        plan.metrics = ["sum_amount_cad", "transaction_count", "avg_amount_cad"]
        plan.sort = [{"field": "month", "direction": "asc"}]
        plan.limit = 24
        plan.visualization = "line"
    elif chart_requested and plan.visualization in {None, "metric", "table"} and plan.tool.startswith("spend."):
        plan.mode = "chart"
        plan.visualization = "bar"
    if _is_policy_retrieval_question(normalized, last_plan):
        return InsightPlan(
            intent="policy_clause_lookup",
            mode="answer",
            tool="policy.retrieveClauses",
            limit=5,
            visualization="table",
        )
    return plan


def maybe_create_global_context_plan(normalized: str, requested_mode: str) -> InsightPlan | None:
    summary_keys: list[str] = []
    intent = "global_app_summary"

    if any(term in normalized for term in (" current system ", " system status ", " overview ", " across the app ", " across the website ")):
        summary_keys = ["dashboard", "review", "approvals", "reports", "policy_setup"]
    elif any(term in normalized for term in (" approvals ", " approval queue ", " waiting for approval ")):
        intent = "approvals_summary"
        summary_keys = ["approvals"]
    elif any(term in normalized for term in (" reports ", " generated reports ", " saved reports ", " report package ")):
        intent = "reports_summary"
        summary_keys = ["reports"]
    elif any(term in normalized for term in (" policy setup ", " policy rules ", " draft rules ", " policy document ", " policy documents ")):
        intent = "policy_setup_summary"
        summary_keys = ["policy_setup"]

    if not summary_keys:
        return None

    return InsightPlan(
        intent=intent,
        mode="table" if requested_mode == "answer" else requested_mode,
        tool="context.globalSummary",
        limit=len(summary_keys),
        visualization="table",
        context_options={"summary_keys": summary_keys},
    )


def _build_department_spend_followup_plan(
    normalized_question: str,
    requested_mode: str,
    mentioned_departments: list[str],
    *,
    chart_requested: bool,
) -> InsightPlan:
    department_filter: str | list[str] = mentioned_departments if len(mentioned_departments) > 1 else mentioned_departments[0]
    period_filters = extract_relative_date_filters(normalized_question)
    time_series_requested = _wants_time_series(normalized_question) or (chart_requested and bool(period_filters))
    category_breakdown_requested = "category" in normalized_question

    if time_series_requested:
        return InsightPlan(
            intent="department_spend_trend",
            mode="chart",
            tool="spend.groupBy",
            filters={"department": department_filter, **period_filters},
            group_by=["month"],
            metrics=["sum_amount_cad", "transaction_count", "avg_amount_cad"],
            sort=[{"field": "month", "direction": "asc"}],
            limit=24,
            visualization="line",
        )

    if chart_requested and category_breakdown_requested:
        return InsightPlan(
            intent="department_spend_by_category",
            mode="chart",
            tool="spend.groupBy",
            filters={"department": department_filter, **period_filters},
            group_by=["business_category"],
            metrics=["sum_amount_cad", "transaction_count", "avg_amount_cad"],
            sort=[{"field": "sum_amount_cad", "direction": "desc"}],
            limit=100,
            visualization="bar",
        )

    return InsightPlan(
        intent="department_spend_summary",
        mode="table" if requested_mode == "table" else "answer",
        tool="spend.summary",
        filters={"department": department_filter, **period_filters},
        metrics=["sum_amount_cad", "transaction_count", "avg_amount_cad"],
        sort=[{"field": "sum_amount_cad", "direction": "desc"}],
        visualization="metric",
    )


def maybe_create_page_context_plan(
    question: str,
    mode: str | None,
    page_context: InsightPageContext | None,
) -> InsightPlan | None:
    if not page_context:
        return None
    normalized = f" {question.lower().strip()} "
    if not _is_page_explanation_question(normalized):
        return None

    requested_mode = mode or "answer"
    route = str(page_context.route or "").strip().lower()
    if route in {"compliance", "approvals"}:
        return InsightPlan(
            intent="review_queue_summary",
            mode="table" if requested_mode == "answer" else requested_mode,
            tool="review.currentQueue",
            filters={"queue_status": "open"},
            metrics=["sum_amount_cad", "transaction_count", "policy_flag_count", "risk_flag_count"],
            sort=[{"field": "review_priority", "direction": "desc"}],
            limit=10,
            visualization="table",
        )

    if route == "dashboard":
        return InsightPlan(
            intent="global_app_summary",
            mode="table" if requested_mode == "answer" else requested_mode,
            tool="context.globalSummary",
            limit=5,
            visualization="table",
            context_options={"summary_keys": ["dashboard", "review", "approvals", "reports", "policy_setup"]},
        )

    if route == "reports":
        return InsightPlan(
            intent="reports_summary",
            mode="table" if requested_mode == "answer" else requested_mode,
            tool="context.globalSummary",
            limit=1,
            visualization="table",
            context_options={"summary_keys": ["reports"]},
        )

    if route == "policyrules":
        return InsightPlan(
            intent="policy_setup_summary",
            mode="table" if requested_mode == "answer" else requested_mode,
            tool="context.globalSummary",
            limit=1,
            visualization="table",
            context_options={"summary_keys": ["policy_setup"]},
        )

    return None


def critic_validate_plan(question: str, plan: InsightPlan) -> InsightValidationResult:
    warnings: list[str] = []
    normalized = question.lower()
    if plan.intent == "spend_summary" and any(term in normalized for term in ["policy", "risk", "merchant", "category", "compare", "review queue", "flagged", "critical"]):
        warnings.append("Planner fell back to a spend summary because the request did not match a supported deterministic intent.")
    if plan.tool == "policy.retrieveClauses":
        warnings.append("Policy clause answers are grounded in indexed policy text, not generated policy interpretation.")
    return InsightValidationResult(valid=True, warnings=warnings)


def validate_plan(plan: InsightPlan) -> InsightValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    payload = plan.model_dump()

    if _contains_disallowed_sql(plan):
        errors.append("Plans cannot contain raw SQL or SQL-like execution fields.")
    if plan.tool not in ALLOWED_TOOLS:
        errors.append(f"Unsupported tool: {plan.tool}.")
    if plan.mode not in ALLOWED_MODES:
        errors.append(f"Unsupported mode: {plan.mode}.")
    if plan.limit > 500:
        errors.append("Plan limit cannot exceed 500.")
    if plan.limit <= 0:
        errors.append("Plan limit must be positive.")

    unknown_metrics = [metric for metric in plan.metrics if metric not in ALLOWED_METRICS]
    unknown_dimensions = [dimension for dimension in plan.group_by if dimension not in ALLOWED_DIMENSIONS]
    unknown_filters = [field for field in plan.filters if field not in ALLOWED_FILTERS]

    if unknown_metrics:
        errors.append(f"Unsupported metrics: {', '.join(unknown_metrics)}.")
    if unknown_dimensions:
        errors.append(f"Unsupported dimensions: {', '.join(unknown_dimensions)}.")
    if unknown_filters:
        errors.append(f"Unsupported filters: {', '.join(unknown_filters)}.")
    for sort_spec in plan.sort:
        field = sort_spec.get("field")
        if field and field not in ALLOWED_METRICS and field not in ALLOWED_DIMENSIONS and field not in {"risk_score", "review_priority", "amount_cad"}:
            errors.append(f"Unsupported sort field: {field}.")

    if plan.tool == "spend.sqlQuery":
        if not (plan.sql_statement or "").strip():
            errors.append("Validated SQL plans must include sql_statement.")
    elif (plan.sql_statement or "").strip():
        errors.append("sql_statement is only allowed for spend.sqlQuery plans.")

    if plan.mode == "report" and not _has_report_scope(plan):
        errors.append("Reports require employee/date range, department/date range, or a named scenario.")
    if not plan.metrics and plan.tool.startswith("spend."):
        warnings.append("Spend tools are more useful with at least one metric.")

    return InsightValidationResult(valid=not errors, errors=errors, warnings=warnings)


def summarize_result(
    plan: InsightPlan,
    rows: list[Any],
    metadata: dict[str, Any],
    citations: list[InsightCitation] | None = None,
) -> str:
    citations = citations or []
    if not rows:
        return "No matching data was found for this request."
    if plan.tool == "spend.compare" and plan.comparison_options:
        return summarize_comparison_result(plan, rows, metadata)
    if plan.tool == "policy.retrieveClauses":
        first = citations[0] if citations else None
        if first:
            title = first.title or first.rule_code or "Policy clause"
            return f"Retrieved {len(citations)} policy clause match(es). Top match: {title}."
        return f"Retrieved {metadata.get('returned_count', len(rows))} policy clause match(es)."
    if plan.tool == "context.globalSummary":
        return summarize_global_context_result(rows, metadata)
    if plan.tool == "review.currentQueue":
        return summarize_review_queue_result(plan, rows, metadata)
    first = rows[0]
    if plan.tool == "spend.topTransactions":
        return summarize_top_transactions_result(plan, rows, metadata)
    if plan.tool == "spend.sqlQuery":
        return summarize_sql_result(plan, rows, metadata)
    total = sum(float(row.values.get("sum_amount_cad") or 0) for row in rows)
    count = sum(int(row.values.get("transaction_count") or 0) for row in rows)
    if plan.tool == "spend.summary":
        return summarize_spend_summary_result(plan, rows)
    if plan.tool == "policy.latestFindings":
        flags = sum(int(row.values.get("policy_flag_count") or 0) for row in rows)
        return f"Found {flags:,} policy-related flags across {len(rows):,} group(s), covering CAD {total:,.2f} in spend."
    if plan.tool == "risk.latestSignals":
        return f"Found {metadata.get('returned_count', len(rows)):,} risk-scored transaction(s) matching the request."
    if plan.tool == "spend.groupBy" and plan.group_by[:1] == ["month"]:
        return summarize_time_series_result(plan, rows)
    if plan.tool == "spend.groupBy":
        return summarize_grouped_spend_result(plan, rows)
    if len(rows) == 1:
        return f"{first.label}: CAD {float(first.values.get('sum_amount_cad') or 0):,.2f} across {int(first.values.get('transaction_count') or 0):,} transaction(s)."
    return f"Top group is {first.label}. Total matching spend is CAD {total:,.2f} across {count:,} transaction(s)."


def compose_insight_response(
    *,
    question: str,
    plan: InsightPlan,
    rows: list[Any],
    metadata: dict[str, Any],
    citations: list[InsightCitation],
    page_context: InsightPageContext | None,
    ask_context: AskContextEnvelope,
    history: list[InsightChatMessage],
    fallback_summary: str,
) -> str:
    contextual_fallback = summarize_contextual_response(question, plan, page_context, ask_context, fallback_summary)
    normalized = f" {question.lower().strip()} "
    if not should_compose_with_ai(question, plan, ask_context, page_context):
        return contextual_fallback

    client = default_insight_response_client()
    if client is None:
        return contextual_fallback

    try:
        answer = client.compose_answer(
            {
                "question": question,
                "fallback_summary": fallback_summary,
                "contextual_fallback": contextual_fallback,
                "plan": plan.model_dump(mode="json"),
                "metadata": metadata,
                "analysis_frame": metadata.get("analysis_frame"),
                "page_context": serialize_page_context(page_context),
                "ask_context": ask_context.model_dump(mode="json"),
                "rows": [row.model_dump(mode="json") if hasattr(row, "model_dump") else row for row in rows[:8]],
                "citations": [citation.model_dump(mode="json") for citation in citations[:3]],
                "recent_history": [
                    {
                        "role": message.role,
                        "content": message.content,
                    }
                    for message in history[-6:]
                    if message.role in {"user", "assistant"} and message.content.strip()
                ],
                "instructions": [
                    "Answer the user's question directly in plain language.",
                    "If the question is about the current page or screen, explain the page first and then connect it to the data.",
                    "If the question spans multiple app areas, synthesize from the provided global summaries before mentioning row-level details.",
                    "If a chart or graph was requested or returned, acknowledge that you plotted or graphed the result and explain what stands out.",
                    "Use the analysis_frame to preserve the current analytical subject, filters, time range, and comparison setup.",
                    "Stay grounded in the supplied totals, counts, statuses, and reviewer context.",
                    "Do not mention internal tools, planner names, or implementation details.",
                ],
            }
        ).strip()
    except Exception:
        return contextual_fallback

    return answer or contextual_fallback


def should_compose_with_ai(
    question: str,
    plan: InsightPlan,
    ask_context: AskContextEnvelope,
    page_context: InsightPageContext | None,
) -> bool:
    normalized = f" {question.lower().strip()} "
    if plan.tool == "context.globalSummary":
        return True
    if page_context and _is_page_explanation_question(normalized):
        return True
    if len(ask_context.context_scope) >= 3 and any(
        term in normalized for term in ("summary", "overview", "report", "approval", "policy setup", "what should", "what are")
    ):
        return True
    return False


def summarize_contextual_response(
    question: str,
    plan: InsightPlan,
    page_context: InsightPageContext | None,
    ask_context: AskContextEnvelope,
    fallback_summary: str,
) -> str:
    if plan.tool == "context.globalSummary":
        return summarize_global_ask_context_response(ask_context, plan, fallback_summary)
    return summarize_page_context_response(question, page_context, fallback_summary)


def summarize_page_context_response(
    question: str,
    page_context: InsightPageContext | None,
    fallback_summary: str,
) -> str:
    normalized = f" {question.lower().strip()} "
    if not page_context or not _is_page_explanation_question(normalized):
        return fallback_summary

    payload = page_context.payload if isinstance(page_context.payload, dict) else {}
    summary = str(payload.get("summary") or "").strip()
    focus = payload.get("focus") if isinstance(payload.get("focus"), dict) else {}
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    details = payload.get("details") if isinstance(payload.get("details"), dict) else {}

    parts = [f"You're on the {page_context.page or 'current'} page."]
    if summary:
        parts.append(summary if summary.endswith(".") else f"{summary}.")

    quick_summary = str(details.get("quick_summary") or "").strip()
    if quick_summary:
        parts.append(quick_summary if quick_summary.endswith(".") else f"{quick_summary}.")

    top_items = details.get("top_items") if isinstance(details.get("top_items"), list) else []
    top_item = top_items[0] if top_items and isinstance(top_items[0], dict) else None
    if top_item:
        merchant = str(top_item.get("merchant") or top_item.get("label") or "the top item")
        status = str(top_item.get("policy_status") or top_item.get("review_level") or "").replace("_", " ").strip()
        amount = top_item.get("amount_cad")
        descriptor = merchant
        if isinstance(amount, (int, float)):
            descriptor = f"{merchant} at CAD {float(amount):,.2f}"
        if status:
            parts.append(f"The highest-priority visible item is {descriptor}, currently marked {status}.")

    elif focus:
        focus_label = str(focus.get("label") or "").strip()
        focus_status = str(focus.get("status") or "").replace("_", " ").strip()
        if focus_label:
            sentence = f"The current focus is {focus_label}"
            if focus_status:
                sentence += f", which is marked {focus_status}"
            parts.append(f"{sentence}.")

    if metrics:
        highlighted = []
        for key in ("open_queue_items", "review_required", "high_or_critical", "policy_violations", "total_scanned"):
            value = metrics.get(key)
            if isinstance(value, (int, float)):
                highlighted.append(f"{key.replace('_', ' ')}: {int(value):,}")
        if highlighted:
            parts.append("Key numbers on this screen include " + ", ".join(highlighted[:4]) + ".")

    return " ".join(part.strip() for part in parts if part.strip()) or fallback_summary


def summarize_global_ask_context_response(
    ask_context: AskContextEnvelope,
    plan: InsightPlan,
    fallback_summary: str,
) -> str:
    summary_keys = [str(key) for key in plan.context_options.get("summary_keys") or []]
    global_summaries = ask_context.global_summaries
    parts: list[str] = []

    if "dashboard" in summary_keys:
        dashboard = global_summaries.get("dashboard") if isinstance(global_summaries.get("dashboard"), dict) else {}
        normalized_count = dashboard.get("normalized_transaction_count")
        department_count = dashboard.get("department_count")
        if isinstance(normalized_count, int) and isinstance(department_count, int):
            parts.append(
                f"The app currently has {normalized_count:,} normalized transactions across {department_count:,} departments."
            )

    if "review" in summary_keys:
        review = global_summaries.get("review") if isinstance(global_summaries.get("review"), dict) else {}
        queue = review.get("queue") if isinstance(review.get("queue"), dict) else {}
        open_items = queue.get("open")
        high_or_critical = queue.get("high_or_critical")
        if isinstance(open_items, int):
            phrase = f"The review queue has {open_items:,} open item(s)"
            if isinstance(high_or_critical, int):
                phrase += f", including {high_or_critical:,} high or critical cases"
            parts.append(phrase + ".")

    if "approvals" in summary_keys:
        approvals = global_summaries.get("approvals") if isinstance(global_summaries.get("approvals"), dict) else {}
        active = approvals.get("active")
        if isinstance(active, int):
            parts.append(f"There are {active:,} active approval request(s) waiting on decisions.")

    if "reports" in summary_keys:
        reports = global_summaries.get("reports") if isinstance(global_summaries.get("reports"), dict) else {}
        report_count = reports.get("report_count")
        top_reports = reports.get("top_reports") if isinstance(reports.get("top_reports"), list) else []
        if isinstance(report_count, int):
            sentence = f"There are {report_count:,} saved report(s)"
            top_report = top_reports[0] if top_reports and isinstance(top_reports[0], dict) else None
            if top_report and top_report.get("label"):
                sentence += f", with {top_report['label']} among the most recent"
            parts.append(sentence + ".")

    if "policy_setup" in summary_keys:
        policy_setup = global_summaries.get("policy_setup") if isinstance(global_summaries.get("policy_setup"), dict) else {}
        active_rules = policy_setup.get("active_rules")
        draft_rules = policy_setup.get("draft_rules")
        latest_document = policy_setup.get("latest_document") if isinstance(policy_setup.get("latest_document"), dict) else {}
        if isinstance(active_rules, int) and isinstance(draft_rules, int):
            sentence = f"Policy setup currently has {active_rules:,} active rule(s) and {draft_rules:,} draft rule(s)"
            if latest_document.get("title"):
                sentence += f", tied to {latest_document['title']}"
            parts.append(sentence + ".")

    if "risk" in summary_keys:
        risk = global_summaries.get("risk") if isinstance(global_summaries.get("risk"), dict) else {}
        returned_scores = risk.get("returned_scores")
        if isinstance(returned_scores, int):
            parts.append(f"The latest risk snapshot includes {returned_scores:,} medium-or-higher scored transaction(s).")

    if ask_context.recent_results:
        latest_summary = str(ask_context.recent_results[-1].get("summary") or "").strip()
        if latest_summary:
            parts.append(f"Recent Ask memory: {latest_summary}")

    return " ".join(parts).strip() or fallback_summary


def infer_columns(rows: list[Any]) -> list[str]:
    columns = ["label"]
    for row in rows:
        for key in row.values:
            if key not in columns:
                columns.append(key)
    return columns


def _blocked_response(
    question: str,
    plan: InsightPlan,
    validation: InsightValidationResult,
    session_id: str | None = None,
) -> InsightQueryResponse:
    return InsightQueryResponse(
        question=question,
        session_id=session_id,
        plan=plan,
        validation=validation,
        summary="The request was not executed because the generated plan failed validation.",
        columns=[],
        rows=[],
        citations=[],
        visualization=None,
        metadata={"blocked": True},
    )


def _contains_blocked_sql(value: Any, *, allowed_keys: set[str] | None = None) -> bool:
    allowed = allowed_keys or set()
    if isinstance(value, dict):
        return any(
            (str(key).lower() in BLOCKED_KEYS and str(key).lower() not in allowed) or _contains_blocked_sql(child, allowed_keys=allowed)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_blocked_sql(item, allowed_keys=allowed) for item in value)
    return False


def _contains_disallowed_sql(plan: InsightPlan) -> bool:
    payload = plan.model_dump(mode="json")
    if plan.tool == "spend.sqlQuery":
        sql_value = payload.pop("sql_statement", None)
        if _contains_blocked_sql(payload):
            return True
        return not isinstance(sql_value, str)
    return _contains_blocked_sql(payload)


def _has_report_scope(plan: InsightPlan) -> bool:
    filters = plan.filters
    has_date_range = bool(filters.get("date_start") and filters.get("date_end"))
    return bool((filters.get("employee") and has_date_range) or (filters.get("department") and has_date_range) or plan.report_options.get("scenario"))


def extract_departments(normalized_question: str) -> list[str]:
    return [
        department
        for department in KNOWN_DEPARTMENTS
        if re.search(rf"\b{re.escape(department.lower())}\b", normalized_question)
    ]


def wants_comparison(normalized_question: str) -> bool:
    haystack = _phrase_match_text(normalized_question)
    return any(token in haystack for token in (" compare ", " compared ", " against ", " versus ", " vs "))


def _wants_chart(normalized_question: str) -> bool:
    haystack = _phrase_match_text(normalized_question)
    return any(term in haystack for term in CHART_REQUEST_TERMS)


def _wants_top_transactions(normalized_question: str) -> bool:
    haystack = _phrase_match_text(normalized_question)
    if any(term in haystack for term in TOP_TRANSACTION_TERMS):
        return True
    if " most expensive " in haystack or " highest spend " in haystack:
        return True
    return (" top " in haystack and " amount " in haystack) or (" top " in haystack and " transaction " in haystack)


def _wants_time_series(normalized_question: str) -> bool:
    haystack = _phrase_match_text(normalized_question)
    return any(term in haystack for term in TIME_SERIES_TERMS)


def _wants_review_queue(normalized_question: str) -> bool:
    haystack = _phrase_match_text(normalized_question)
    return any(term in haystack for term in REVIEW_QUEUE_TERMS)


def _is_review_summary_question(normalized_question: str) -> bool:
    haystack = _phrase_match_text(normalized_question)
    return any(term in haystack for term in (" summarize ", " summary ", " current ", " overview "))


def _wants_review_explanation(normalized_question: str) -> bool:
    haystack = _phrase_match_text(normalized_question)
    return any(term in haystack for term in (" why ", " explain ", " reason ", " reasons "))


def _is_page_explanation_question(normalized_question: str) -> bool:
    haystack = _phrase_match_text(normalized_question)
    return any(term in haystack for term in PAGE_EXPLANATION_TERMS)


def _looks_like_contextual_followup(
    normalized_question: str,
    last_analysis_frame: dict[str, Any] | None,
) -> bool:
    haystack = _phrase_match_text(normalized_question)
    if any(term in haystack for term in (" what about ", " how about ", " and ", " show me ", " graph ", " chart ", " trend ")):
        return True
    if not last_analysis_frame:
        return False
    if extract_departments(normalized_question) and any(
        term in haystack for term in (" spend ", " spending ", " expense ", " expenses ", " department ")
    ):
        return True
    return bool(last_analysis_frame.get("analysis_kind") and len(normalized_question.split()) <= 8)


def _is_department_spend_followup(
    normalized_question: str,
    last_plan: InsightPlan | None,
    last_analysis_frame: dict[str, Any] | None,
) -> bool:
    mentioned_departments = extract_departments(normalized_question)
    if not mentioned_departments:
        return False
    haystack = _phrase_match_text(normalized_question)
    if any(term in haystack for term in (" spend ", " spending ", " expense ", " expenses ")):
        return True
    if not last_plan and not last_analysis_frame:
        return False
    prior_kind = str((last_analysis_frame or {}).get("analysis_kind") or "")
    if prior_kind in {"department_spend", "department_trend", "department_comparison", "top_transactions"} and any(
        term in haystack for term in (" what about ", " how about ", " graph ", " chart ", " last quarter ", " this quarter ", " trend ")
    ):
        return True
    return False


def _extract_requested_limit(normalized_question: str, default: int) -> int:
    if "top three" in normalized_question or "top 3" in normalized_question:
        return 3
    match = re.search(r"\btop\s+(\d{1,3})\b", normalized_question)
    if match:
        return max(1, min(500, int(match.group(1))))
    return default


def extract_relative_date_filters(normalized_question: str, today: date | None = None) -> dict[str, str]:
    current_day = today or date.today()
    haystack = _phrase_match_text(normalized_question)
    if " last quarter " in haystack:
        start, end = _quarter_date_range(current_day, offset=-1)
        return {"date_start": start.isoformat(), "date_end": end.isoformat()}
    if " this quarter " in haystack or " current quarter " in haystack:
        start, end = _quarter_date_range(current_day, offset=0)
        return {"date_start": start.isoformat(), "date_end": end.isoformat()}
    if " last month " in haystack:
        start, end = _month_date_range(current_day, offset=-1)
        return {"date_start": start.isoformat(), "date_end": end.isoformat()}
    if " this month " in haystack or " current month " in haystack:
        start, end = _month_date_range(current_day, offset=0)
        return {"date_start": start.isoformat(), "date_end": end.isoformat()}
    if " last year " in haystack:
        start = date(current_day.year - 1, 1, 1)
        end = date(current_day.year - 1, 12, 31)
        return {"date_start": start.isoformat(), "date_end": end.isoformat()}
    if " this year " in haystack or " current year " in haystack:
        start = date(current_day.year, 1, 1)
        end = date(current_day.year, 12, 31)
        return {"date_start": start.isoformat(), "date_end": end.isoformat()}
    return {}


def _quarter_date_range(current_day: date, offset: int) -> tuple[date, date]:
    quarter_index = (current_day.month - 1) // 3
    absolute_quarter = current_day.year * 4 + quarter_index + offset
    year = absolute_quarter // 4
    quarter = absolute_quarter % 4
    start_month = quarter * 3 + 1
    start = date(year, start_month, 1)
    if start_month == 10:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, start_month + 3, 1) - timedelta(days=1)
    return start, end


def _month_date_range(current_day: date, offset: int) -> tuple[date, date]:
    absolute_month = current_day.year * 12 + (current_day.month - 1) + offset
    year = absolute_month // 12
    month = absolute_month % 12 + 1
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start, end


def _phrase_match_text(value: str) -> str:
    compact = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    return f" {compact} "


def _is_chart_result(plan: InsightPlan) -> bool:
    return plan.mode == "chart" or plan.visualization in {"bar", "line", "pie"}


def _format_filter_subject(filters: dict[str, Any]) -> str:
    if filters.get("department") not in (None, "", []):
        return f"{_format_filter_value(filters.get('department'))} spend"
    if filters.get("employee") not in (None, "", []):
        return f"{_format_filter_value(filters.get('employee'))} spend"
    if filters.get("merchant") not in (None, "", []):
        return f"{_format_filter_value(filters.get('merchant'))} spend"
    return "All matching spend"


def _format_filter_value(value: Any) -> str:
    if isinstance(value, list):
        labels = [str(item) for item in value if str(item).strip()]
        if not labels:
            return ""
        if len(labels) == 1:
            return labels[0]
        return ", ".join(labels[:-1]) + f" and {labels[-1]}"
    return str(value)


def _format_date_scope(filters: dict[str, Any]) -> str:
    start_value = filters.get("date_start")
    end_value = filters.get("date_end")
    if not start_value or not end_value:
        return ""
    try:
        start_date = date.fromisoformat(str(start_value))
        end_date = date.fromisoformat(str(end_value))
    except Exception:
        return f" from {start_value} to {end_value}"
    if start_date.day == 1 and end_date.day >= 28:
        if start_date.year == end_date.year and start_date.month == end_date.month:
            return f" for {start_date.strftime('%B %Y')}"
        return f" from {start_date.strftime('%B %Y')} to {end_date.strftime('%B %Y')}"
    return f" from {start_date.isoformat()} to {end_date.isoformat()}"


def summarize_spend_summary_result(plan: InsightPlan, rows: list[Any]) -> str:
    first = rows[0]
    total = float(first.values.get("sum_amount_cad") or 0)
    count = int(first.values.get("transaction_count") or 0)
    if not plan.filters:
        return f"All matching spend: CAD {total:,.2f} across {count:,} transaction(s)."

    subject = _format_filter_subject(plan.filters)
    return f"{subject} totaled CAD {total:,.2f} across {count:,} transaction(s){_format_date_scope(plan.filters)}."


def summarize_top_transactions_result(plan: InsightPlan, rows: list[Any], metadata: dict[str, Any]) -> str:
    first = rows[0]
    first_amount = float(first.values.get("amount_cad") or first.values.get("sum_amount_cad") or 0)
    total = sum(float(row.values.get("amount_cad") or row.values.get("sum_amount_cad") or 0) for row in rows)
    scope = " from the current table" if plan.filters.get("transaction_ids") else ""
    if _is_chart_result(plan):
        return (
            f"I plotted the top {metadata.get('returned_count', len(rows)):,} transaction(s) by amount{scope}. "
            f"Top transaction is {first.label} at CAD {first_amount:,.2f}, and these results total CAD {total:,.2f}."
        )
    return (
        f"Top transaction is {first.label} at CAD {first_amount:,.2f}. "
        f"Returned {metadata.get('returned_count', len(rows)):,} transaction(s) totaling CAD {total:,.2f}."
    )


def summarize_time_series_result(plan: InsightPlan, rows: list[Any]) -> str:
    first = rows[0]
    total = sum(float(row.values.get("sum_amount_cad") or 0) for row in rows)
    count = sum(int(row.values.get("transaction_count") or 0) for row in rows)
    top_month = first.label
    top_month_total = float(first.values.get("sum_amount_cad") or 0)
    subject = _format_filter_subject(plan.filters)
    date_scope = _format_date_scope(plan.filters)
    if _is_chart_result(plan):
        return (
            f"I plotted {subject} by month{date_scope}. "
            f"Total spend was CAD {total:,.2f} across {count:,} transaction(s), and the highest month was {top_month} at CAD {top_month_total:,.2f}."
        )
    return f"Total matching spend is CAD {total:,.2f} across {count:,} transaction(s). The highest month is {top_month} at CAD {top_month_total:,.2f}."


def summarize_grouped_spend_result(plan: InsightPlan, rows: list[Any]) -> str:
    first = rows[0]
    total = sum(float(row.values.get("sum_amount_cad") or 0) for row in rows)
    count = sum(int(row.values.get("transaction_count") or 0) for row in rows)
    group_label = str(plan.group_by[0] if plan.group_by else "group").replace("_", " ")
    subject = _format_filter_subject(plan.filters)
    if _is_chart_result(plan):
        return (
            f"I grouped {subject} by {group_label}. "
            f"The largest {group_label} is {first.label} at CAD {float(first.values.get('sum_amount_cad') or 0):,.2f}, "
            f"with CAD {total:,.2f} across {count:,} transaction(s) overall."
        )
    return f"Top group is {first.label}. Total matching spend is CAD {total:,.2f} across {count:,} transaction(s)."


def summarize_comparison_result(plan: InsightPlan, rows: list[Any], metadata: dict[str, Any]) -> str:
    targets = [str(target) for target in plan.comparison_options.get("targets") or []]
    if len(targets) < 2:
        return f"Compared {metadata.get('returned_count', len(rows)):,} grouped result(s)."

    left_slug = slugify_target(targets[0])
    right_slug = slugify_target(targets[1])
    left_total = sum(float(row.values.get(f"{left_slug}_sum_amount_cad") or 0) for row in rows)
    right_total = sum(float(row.values.get(f"{right_slug}_sum_amount_cad") or 0) for row in rows)
    delta = left_total - right_total
    top_group = rows[0].label
    direction = "higher" if delta >= 0 else "lower"
    return (
        f"Compared {targets[0]} against {targets[1]} across {len(rows):,} group(s). "
        f"Top group is {top_group}. {targets[0]} spend is CAD {left_total:,.2f}, "
        f"{targets[1]} spend is CAD {right_total:,.2f}, so {targets[0]} is CAD {abs(delta):,.2f} {direction}."
    )


def summarize_review_queue_result(plan: InsightPlan, rows: list[Any], metadata: dict[str, Any]) -> str:
    total = int(metadata.get("queue_total") or metadata.get("returned_count") or len(rows))
    open_count = int(metadata.get("queue_open") or 0)
    critical_count = int(metadata.get("queue_critical") or 0)
    high_count = int(metadata.get("queue_high") or 0)
    policy_flagged = int(metadata.get("queue_policy_flagged") or 0)
    risk_flagged = int(metadata.get("queue_risk_flagged") or 0)

    if plan.intent == "review_queue_explanation" and rows:
        explanations: list[str] = []
        for row in rows[:3]:
            reason = str(row.values.get("reason_summary") or "they combine policy and risk signals that need reviewer attention")
            explanations.append(f"{row.label}: {reason}")
        prefix = f"The top {len(explanations)} flagged item(s) are critical because "
        return prefix + "; ".join(explanations) + "."

    return (
        f"The current review queue has {total:,} item(s), with {open_count:,} open, "
        f"{critical_count:,} critical, and {high_count:,} high priority. "
        f"{policy_flagged:,} have policy concerns and {risk_flagged:,} carry risk signals."
    )


def summarize_sql_result(plan: InsightPlan, rows: list[Any], metadata: dict[str, Any]) -> str:
    if not rows:
        return "No matching data was returned from the validated SQL query."

    first = rows[0]
    amount_value = first.values.get("amount_cad") or first.values.get("sum_amount_cad") or first.values.get("avg_amount_cad")
    if len(rows) == 1 and isinstance(amount_value, (int, float)):
        return f"{first.label}: CAD {float(amount_value):,.2f}."

    if isinstance(amount_value, (int, float)):
        prefix = f"Returned {metadata.get('returned_count', len(rows)):,} row(s)."
        if _is_chart_result(plan):
            return f"{prefix} I plotted the result set, and the leading value is {first.label} at CAD {float(amount_value):,.2f}."
        return f"{prefix} Top result is {first.label} at CAD {float(amount_value):,.2f}."

    return f"Returned {metadata.get('returned_count', len(rows)):,} row(s) from the validated SQL query."


def summarize_global_context_result(rows: list[Any], metadata: dict[str, Any]) -> str:
    if not rows:
        return "No global app context was available for this question."
    labels = ", ".join(row.label for row in rows[:4])
    return f"Pulled {metadata.get('returned_count', len(rows))} app-wide summary view(s): {labels}."


def slugify_target(value: str) -> str:
    return "_".join(part for part in value.strip().lower().replace("&", "and").split() if part)


def apply_page_context_to_plan(
    plan: InsightPlan,
    page_context: InsightPageContext | None,
) -> InsightPlan:
    if not page_context:
        return plan
    context_filters = extract_context_filters(page_context)
    if not context_filters:
        return plan
    next_plan = plan.model_copy(deep=True)
    for key, value in context_filters.items():
        if next_plan.filters.get(key) in (None, "", []):
            next_plan.filters[key] = value
    return next_plan


def extract_context_filters(page_context: InsightPageContext | None) -> dict[str, Any]:
    if not page_context:
        return {}
    payload = page_context.payload if isinstance(page_context.payload, dict) else {}
    root_payload = {
        key: value
        for key, value in payload.items()
        if key not in {"details", "metrics", "suggestions", "focus_entities", "visible_entities", "artifacts", "available_views"}
    }
    sources = [
        payload.get("filters") if isinstance(payload.get("filters"), dict) else None,
        payload.get("focus") if isinstance(payload.get("focus"), dict) else None,
        root_payload,
    ]
    filters: dict[str, Any] = {}
    for filter_name, aliases in CONTEXT_FILTER_ALIAS_MAP.items():
        for source in sources:
            value = _find_context_value(source, aliases)
            if value in (None, "", []):
                continue
            filters[filter_name] = value
            break
    return filters


def metadata_with_context(
    metadata: dict[str, Any],
    page_context: InsightPageContext | None,
    ask_context: AskContextEnvelope,
    plan: InsightPlan,
    citations: list[InsightCitation],
    analysis_frame: dict[str, Any],
) -> dict[str, Any]:
    return {
        **metadata,
        "page_context": serialize_page_context(page_context),
        "ask_context": ask_context.model_dump(mode="json"),
        "grounding_sources": grounding_sources_for_result(plan, page_context, ask_context, citations),
        "referenced_entities": [
            entity.model_dump(mode="json")
            for entity in [*ask_context.focus_entities, *ask_context.visible_entities[:5]]
        ],
        "artifact_capabilities": artifact_capabilities_for_result(plan),
        "context_scope": ask_context.context_scope,
        "analysis_frame": analysis_frame,
    }


def grounding_sources_for_result(
    plan: InsightPlan,
    page_context: InsightPageContext | None,
    ask_context: AskContextEnvelope,
    citations: list[InsightCitation],
) -> list[str]:
    sources: list[str] = []
    if page_context:
        sources.append("page_context")
    if plan.tool == "spend.sqlQuery":
        sources.append("validated_sql")
    elif plan.tool != "context.globalSummary":
        sources.append("db_query")
    else:
        sources.append("global_summary")
    if citations:
        sources.append("policy_rag")
    if ask_context.artifacts or ask_context.recent_artifacts:
        sources.append("report_artifact")
    if ask_context.recent_results:
        sources.append("session_memory")
    return sources


def artifact_capabilities_for_result(plan: InsightPlan) -> list[str]:
    capabilities = ["brief", "csv", "diagram"]
    if plan.mode == "chart" or plan.visualization in {"bar", "line", "pie"}:
        capabilities.append("chart")
    return capabilities


def serialize_page_context(page_context: InsightPageContext | None) -> dict[str, Any] | None:
    if not page_context:
        return None
    payload = page_context.model_dump(mode="json")
    if payload.get("payload") == {}:
        payload["payload"] = {}
    return payload


def build_analysis_frame(
    *,
    question: str,
    plan: InsightPlan,
    rows: list[Any],
    page_context: InsightPageContext | None,
) -> dict[str, Any]:
    return {
        "question": question,
        "analysis_kind": infer_analysis_kind(plan),
        "tool": plan.tool,
        "intent": plan.intent,
        "mode": plan.mode,
        "visualization": plan.visualization,
        "filters": plan.filters,
        "group_by": plan.group_by,
        "comparison_targets": plan.comparison_options.get("targets") or [],
        "focus_labels": [row.label for row in rows[:5]],
        "page": page_context.page if page_context else None,
        "route": page_context.route if page_context else None,
    }


def infer_analysis_kind(plan: InsightPlan) -> str:
    if plan.tool == "spend.topTransactions":
        return "top_transactions"
    if plan.tool == "spend.compare" and plan.comparison_options.get("dimension") == "department":
        return "department_comparison"
    if plan.tool == "spend.groupBy" and plan.group_by[:1] == ["month"] and plan.filters.get("department"):
        return "department_trend"
    if plan.tool == "spend.summary" and plan.filters.get("department"):
        return "department_spend"
    if plan.tool == "review.currentQueue":
        return "review_queue"
    if plan.tool == "context.globalSummary":
        return "global_summary"
    return plan.intent


def _ensure_session(
    session_id: str | None,
    question: str,
    page_context: InsightPageContext | None = None,
) -> InsightSession:
    if session_id:
        session = _fetch_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Insight session was not found.")
        return session
    return create_insight_session(InsightSessionCreateRequest(initial_question=question, page_context=page_context))


def _fetch_session(session_id: str) -> InsightSession | None:
    rows = (
        get_supabase_client()
        .table("chat_sessions")
        .select("*")
        .eq("id", session_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    return _session_from_row(rows[0]) if rows else None


def _load_session_messages(
    session_id: str,
    limit: int = 24,
    *,
    include_context_messages: bool = True,
) -> list[InsightChatMessage]:
    rows = (
        get_supabase_client()
        .table("chat_messages")
        .select("*")
        .eq("session_id", session_id)
        .order("created_at")
        .limit(limit)
        .execute()
        .data
        or []
    )
    messages = [_message_from_row(row) for row in rows]
    if include_context_messages:
        return messages
    return [message for message in messages if not _is_context_message(message)]


def _persist_query_exchange(
    session_id: str,
    question: str,
    response: InsightQueryResponse,
    *,
    page_context: InsightPageContext | None = None,
) -> None:
    client = get_supabase_client()
    client.table("chat_messages").insert(
        {
            "session_id": session_id,
            "role": "user",
            "content": question,
            "metadata": {
                "kind": "insight_question",
                "page_context": serialize_page_context(page_context),
            },
        }
    ).execute()
    client.table("chat_messages").insert(
        {
            "session_id": session_id,
            "role": "assistant",
            "content": response.summary,
            "metadata": {
                "kind": "insight_response",
                "question": response.question,
                "summary": response.summary,
                "analysis_frame": response.metadata.get("analysis_frame"),
                "session_id": response.session_id,
                "plan": response.plan.model_dump(mode="json"),
                "validation": response.validation.model_dump(mode="json"),
                "planner_source": response.planner_source,
                "columns": response.columns,
                "rows": [row.model_dump(mode="json") for row in response.rows[:12]],
                "artifact_rows": [row.model_dump(mode="json") for row in response.rows],
                "visualization": response.visualization,
                "citations": [citation.model_dump(mode="json") for citation in response.citations],
                "metadata": response.metadata,
                "page_context": serialize_page_context(page_context),
            },
        }
    ).execute()


def _persist_session_context(session_id: str, page_context: InsightPageContext | None) -> None:
    if not page_context:
        return
    existing = _extract_latest_page_context(_load_session_messages(session_id, limit=6, include_context_messages=True))
    if existing and existing.model_dump(mode="json") == page_context.model_dump(mode="json"):
        return
    get_supabase_client().table("chat_messages").insert(
        {
            "session_id": session_id,
            "role": "system",
            "content": "Session context captured.",
            "metadata": {
                "kind": "session_context",
                "page_context": serialize_page_context(page_context),
            },
        }
    ).execute()


def _extract_last_assistant_plan(messages: list[InsightChatMessage]) -> InsightPlan | None:
    for message in reversed(messages):
        if message.role != "assistant":
            continue
        plan_payload = message.metadata.get("plan") if isinstance(message.metadata, dict) else None
        if isinstance(plan_payload, dict):
            try:
                return InsightPlan(**plan_payload)
            except Exception:
                continue
    return None


def _extract_last_analysis_frame(messages: list[InsightChatMessage]) -> dict[str, Any] | None:
    for message in reversed(messages):
        if message.role != "assistant":
            continue
        metadata = message.metadata if isinstance(message.metadata, dict) else {}
        frame = metadata.get("analysis_frame")
        if isinstance(frame, dict):
            return frame
        nested_metadata = metadata.get("metadata") if isinstance(metadata.get("metadata"), dict) else {}
        nested_frame = nested_metadata.get("analysis_frame")
        if isinstance(nested_frame, dict):
            return nested_frame
    return None


def _extract_latest_page_context(messages: list[InsightChatMessage]) -> InsightPageContext | None:
    for message in reversed(messages):
        metadata = message.metadata if isinstance(message.metadata, dict) else {}
        payload = metadata.get("page_context")
        if isinstance(payload, dict):
            try:
                return InsightPageContext(**payload)
            except Exception:
                continue
    return None


def _should_try_ai_plan(question: str, plan: InsightPlan, history: list[InsightChatMessage]) -> bool:
    normalized = f" {question.lower().strip()} "
    if any(hint in normalized for hint in FOLLOW_UP_HINTS):
        return True
    if _is_policy_retrieval_question(normalized, _extract_last_assistant_plan(history)):
        return True
    if _wants_top_transactions(normalized) or any(term in _phrase_match_text(normalized) for term in TABLE_REFERENCE_TERMS):
        return True
    return plan.intent == "spend_summary" and any(
        term in normalized
        for term in [
            "policy",
            "risk",
            "merchant",
            "category",
            "compare",
            "review queue",
            "flagged",
            "critical",
            "chart",
            "graph",
            "quarter",
            "table",
            "reports",
            "approvals",
            "system status",
            "overview",
        ]
    )


def _is_policy_retrieval_question(normalized_question: str, last_plan: InsightPlan | None) -> bool:
    haystack = _phrase_match_text(normalized_question)
    if any(term in haystack for term in POLICY_RETRIEVAL_TERMS):
        return True
    if " what does policy say " in haystack or " what does the policy say " in haystack:
        return True
    return bool(last_plan and last_plan.tool.startswith("policy.") and any(hint in haystack for hint in FOLLOW_UP_HINTS))


def _session_from_row(row: dict[str, Any]) -> InsightSession:
    return InsightSession(
        id=str(row["id"]),
        title=str(row.get("title") or "Talk to Data"),
        created_by_employee_id=str(row.get("created_by_employee_id")) if row.get("created_by_employee_id") else None,
        created_at=str(row.get("created_at")) if row.get("created_at") else None,
        updated_at=str(row.get("updated_at")) if row.get("updated_at") else None,
    )


def _message_from_row(row: dict[str, Any]) -> InsightChatMessage:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    return InsightChatMessage(
        id=str(row["id"]) if row.get("id") else None,
        session_id=str(row.get("session_id")) if row.get("session_id") else None,
        role=row.get("role") or "assistant",
        content=str(row.get("content") or ""),
        metadata=_sanitize_message_metadata(metadata),
        created_at=str(row.get("created_at")) if row.get("created_at") else None,
    )


def _find_context_value(payload: Any, aliases: tuple[str, ...]) -> Any:
    if not isinstance(payload, dict):
        return None
    for alias in aliases:
        if alias in payload:
            value = _normalize_context_value(payload.get(alias))
            if value not in (None, "", []):
                return value
    for value in payload.values():
        if isinstance(value, dict):
            nested = _find_context_value(value, aliases)
            if nested not in (None, "", []):
                return nested
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    nested = _find_context_value(item, aliases)
                    if nested not in (None, "", []):
                        return nested
    return None


def _normalize_context_value(value: Any) -> Any:
    if isinstance(value, dict):
        for key in ("name", "label", "value"):
            if value.get(key) not in (None, "", []):
                return value.get(key)
        return None
    if isinstance(value, list):
        normalized = [_normalize_context_value(item) for item in value]
        compact = [item for item in normalized if item not in (None, "", [])]
        return compact or None
    return value


def _is_context_message(message: InsightChatMessage) -> bool:
    return bool(isinstance(message.metadata, dict) and message.metadata.get("kind") == "session_context")


def _sanitize_message_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    if metadata.get("kind") != "insight_response":
        return metadata
    sanitized = dict(metadata)
    sanitized.pop("artifact_rows", None)
    return sanitized
