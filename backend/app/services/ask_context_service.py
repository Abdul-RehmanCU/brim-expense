from __future__ import annotations

from collections import Counter
from typing import Any

from app.database.supabase_client import get_supabase_client
from app.schemas.insights import (
    AskContextArtifact,
    AskContextEntity,
    AskContextEnvelope,
    InsightChatMessage,
    InsightPageContext,
    InsightPlan,
    InsightResultRow,
)
from app.services.approvals_service import list_approvals
from app.services.policy_service import get_policy_summary, list_policy_rules
from app.services.reports_service import get_report, list_reports
from app.services.review_queue_service import list_review_queue, summarize_review_queue
from app.services.risk_service import list_risk_scores
from app.services.transactions_service import get_transactions_summary

RECENT_RESULT_LIMIT = 4
VISIBLE_ENTITY_HYDRATION_LIMIT = 5


def build_ask_context_envelope(
    *,
    page_context: InsightPageContext | None,
    history: list[InsightChatMessage],
) -> AskContextEnvelope:
    focus_entities = extract_context_entities(page_context, "focus_entities")
    visible_entities = extract_context_entities(page_context, "visible_entities")
    artifacts = extract_context_artifacts(page_context)
    hydrated_entities = hydrate_entities([*focus_entities, *visible_entities[:VISIBLE_ENTITY_HYDRATION_LIMIT]])
    recent_results = extract_recent_results(history)
    recent_artifacts = extract_recent_artifacts(history)
    global_summaries = build_global_summaries()
    context_scope = derive_context_scope(
        page_context=page_context,
        focus_entities=focus_entities,
        visible_entities=visible_entities,
        artifacts=artifacts,
        recent_results=recent_results,
        hydrated_entities=hydrated_entities,
    )
    return AskContextEnvelope(
        page_context=page_context,
        focus_entities=focus_entities,
        visible_entities=visible_entities,
        artifacts=artifacts,
        global_summaries=global_summaries,
        hydrated_entities=hydrated_entities,
        recent_results=recent_results,
        recent_artifacts=recent_artifacts,
        context_scope=context_scope,
    )


def execute_context_summary_tool(
    plan: InsightPlan,
    ask_context: AskContextEnvelope,
    question: str,
) -> tuple[list[InsightResultRow], dict[str, Any], list[Any]]:
    raw_summary_keys = plan.context_options.get("summary_keys")
    summary_keys = [str(key) for key in raw_summary_keys] if isinstance(raw_summary_keys, list) else []
    if raw_summary_keys is None and not summary_keys:
        summary_keys = infer_summary_keys(question)

    rows: list[InsightResultRow] = []
    for summary_key in summary_keys:
        row = _summary_row_for_key(summary_key, ask_context)
        if row is not None:
            rows.append(row)

    if not rows:
        rows = [
            InsightResultRow(
                label="Current app context",
                values={
                    "page": ask_context.page_context.page if ask_context.page_context else None,
                    "route": ask_context.page_context.route if ask_context.page_context else None,
                    "visible_entities": len(ask_context.visible_entities),
                    "recent_results": len(ask_context.recent_results),
                },
            )
        ]

    metadata = {
        "record_count": len(rows),
        "returned_count": len(rows),
        "summary_keys": summary_keys,
    }
    return rows, metadata, []


def infer_summary_keys(question: str) -> list[str]:
    normalized = question.lower()
    if any(term in normalized for term in ("approval", "approvals", "manager")):
        return ["approvals"]
    if any(term in normalized for term in ("report", "reports", "brief", "csv", "artifact")):
        return ["reports"]
    if any(term in normalized for term in ("policy", "rule", "rules", "document", "documents")):
        return ["policy_setup"]
    if any(term in normalized for term in ("risk", "critical signals", "high risk")):
        return ["risk"]
    if any(term in normalized for term in ("review", "queue", "flagged", "attention")):
        return ["review"]
    if any(term in normalized for term in ("transaction", "transactions", "import", "imported")):
        return ["dashboard", "transactions"]
    return ["dashboard", "review", "approvals", "reports", "policy_setup"]


def extract_context_entities(page_context: InsightPageContext | None, key: str) -> list[AskContextEntity]:
    payload = page_context.payload if page_context and isinstance(page_context.payload, dict) else {}
    raw_entities = payload.get(key)
    if not isinstance(raw_entities, list):
        raw_entities = []

    entities: list[AskContextEntity] = []
    for raw_entity in raw_entities:
        if not isinstance(raw_entity, dict):
            continue
        label = str(raw_entity.get("label") or "").strip()
        entity_type = str(raw_entity.get("type") or "").strip()
        if not label or not entity_type:
            continue
        attributes = raw_entity.get("attributes") if isinstance(raw_entity.get("attributes"), dict) else {}
        entities.append(
            AskContextEntity(
                type=entity_type,
                id=str(raw_entity.get("id")) if raw_entity.get("id") else None,
                label=label,
                status=str(raw_entity.get("status")) if raw_entity.get("status") else None,
                attributes=attributes,
            )
        )

    if entities:
        return entities

    legacy_focus = payload.get("focus") if isinstance(payload.get("focus"), dict) else None
    if key == "focus_entities" and legacy_focus and legacy_focus.get("label") and legacy_focus.get("type"):
        return [
            AskContextEntity(
                type=str(legacy_focus.get("type")),
                id=str(legacy_focus.get("id")) if legacy_focus.get("id") else None,
                label=str(legacy_focus.get("label")),
                status=str(legacy_focus.get("status")) if legacy_focus.get("status") else None,
                attributes={},
            )
        ]
    return []


def extract_context_artifacts(page_context: InsightPageContext | None) -> list[AskContextArtifact]:
    payload = page_context.payload if page_context and isinstance(page_context.payload, dict) else {}
    raw_artifacts = payload.get("artifacts")
    if not isinstance(raw_artifacts, list):
        return []

    artifacts: list[AskContextArtifact] = []
    for raw_artifact in raw_artifacts:
        if not isinstance(raw_artifact, dict):
            continue
        artifact_type = str(raw_artifact.get("type") or "").strip()
        label = str(raw_artifact.get("label") or "").strip()
        if not artifact_type or not label:
            continue
        metadata = raw_artifact.get("metadata") if isinstance(raw_artifact.get("metadata"), dict) else {}
        artifacts.append(
            AskContextArtifact(
                type=artifact_type,
                id=str(raw_artifact.get("id")) if raw_artifact.get("id") else None,
                label=label,
                status=str(raw_artifact.get("status")) if raw_artifact.get("status") else None,
                metadata=metadata,
            )
        )
    return artifacts


def build_global_summaries() -> dict[str, Any]:
    return {
        "dashboard": safe_build_dashboard_summary(),
        "transactions": safe_build_transactions_summary(),
        "review": safe_build_review_summary(),
        "risk": safe_build_risk_summary(),
        "approvals": safe_build_approvals_summary(),
        "reports": safe_build_reports_summary(),
        "policy_setup": safe_build_policy_setup_summary(),
    }


def safe_build_dashboard_summary() -> dict[str, Any]:
    try:
        summary = get_transactions_summary()
        return summary.model_dump(mode="json")
    except Exception:
        return {}


def safe_build_transactions_summary() -> dict[str, Any]:
    try:
        summary = get_transactions_summary()
        return {
            "normalized_transaction_count": summary.normalized_transaction_count,
            "raw_transaction_count": summary.raw_transaction_count,
            "employee_count": summary.employee_count,
            "department_count": summary.department_count,
        }
    except Exception:
        return {}


def safe_build_review_summary() -> dict[str, Any]:
    try:
        policy_summary = get_policy_summary().model_dump(mode="json")
    except Exception:
        policy_summary = {}
    try:
        queue_items = list_review_queue(limit=10, queue_status="open")
        queue_summary = summarize_review_queue(queue_items).model_dump(mode="json")
        queue_summary["top_items"] = [
            {
                "transaction_id": item.transaction_id,
                "merchant": item.merchant,
                "amount_cad": item.amount_cad,
                "review_level": item.review_level,
                "policy_status": item.policy_status,
                "risk_level": item.risk_level,
            }
            for item in queue_items[:3]
        ]
    except Exception:
        queue_summary = {}
    return {"policy": policy_summary, "queue": queue_summary}


def safe_build_risk_summary() -> dict[str, Any]:
    try:
        scores = list_risk_scores(min_level="medium", limit=25)
    except Exception:
        return {}
    counts = Counter(score.risk_level for score in scores if score.risk_level)
    return {
        "returned_scores": len(scores),
        "level_counts": dict(counts),
        "top_signals": [
            {
                "transaction_id": score.transaction_id,
                "merchant": score.merchant,
                "amount_cad": score.amount_cad,
                "risk_level": score.risk_level,
                "risk_score": score.risk_score,
            }
            for score in scores[:5]
        ],
    }


def safe_build_approvals_summary() -> dict[str, Any]:
    try:
        approvals = list_approvals(limit=25).approvals
    except Exception:
        return {}
    active = [approval for approval in approvals if approval.status in {"draft", "requested"}]
    return {
        "total": len(approvals),
        "active": len(active),
        "decided": len(approvals) - len(active),
        "top_items": [
            {
                "approval_id": approval.id,
                "merchant": approval.merchant,
                "requested_amount_cad": approval.requested_amount_cad,
                "status": approval.status,
                "policy_status": approval.policy_status,
                "risk_level": approval.risk_level,
            }
            for approval in active[:5]
        ],
    }


def safe_build_reports_summary() -> dict[str, Any]:
    try:
        reports = list_reports(limit=10).reports
    except Exception:
        return {}
    return {
        "report_count": len(reports),
        "top_reports": [
            {
                "report_id": report.id,
                "label": report.report_name or report.employee_name or report.id,
                "status": report.status,
                "item_count": report.item_count,
                "total_amount_cad": report.total_amount_cad,
            }
            for report in reports[:5]
        ],
    }


def safe_build_policy_setup_summary() -> dict[str, Any]:
    try:
        rules = list_policy_rules(limit=100)
    except Exception:
        rules = []
    active_rules = [rule for rule in rules if rule.status == "active"]
    draft_rules = [rule for rule in rules if rule.status == "draft"]
    latest_document = fetch_latest_policy_document()
    return {
        "rule_count": len(rules),
        "active_rules": len(active_rules),
        "draft_rules": len(draft_rules),
        "latest_document": latest_document,
    }


def fetch_latest_policy_document() -> dict[str, Any] | None:
    try:
        rows = (
            get_supabase_client()
            .table("policy_documents")
            .select("id,title,source_type,extraction_status,active,updated_at")
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
            .data
            or []
        )
    except Exception:
        return None
    if not rows:
        return None
    row = rows[0]
    return {
        "id": row.get("id"),
        "title": row.get("title"),
        "source_type": row.get("source_type"),
        "extraction_status": row.get("extraction_status"),
        "active": row.get("active"),
        "updated_at": row.get("updated_at"),
    }


def hydrate_entities(entities: list[AskContextEntity]) -> dict[str, Any]:
    hydrated: dict[str, Any] = {}
    for entity in entities:
        key = f"{entity.type}:{entity.id or entity.label}"
        facts = hydrate_entity(entity)
        if facts:
            hydrated[key] = facts
    return hydrated


def hydrate_entity(entity: AskContextEntity) -> dict[str, Any] | None:
    if entity.type == "expense_report" and entity.id:
        try:
            report = get_report(entity.id)
            return {
                "report_id": report.id,
                "label": report.report_name or report.employee_name or report.id,
                "status": report.status,
                "item_count": report.item_count,
                "total_amount_cad": report.total_amount_cad,
                "policy_flag_count": report.policy_flag_count,
                "risk_flag_count": report.risk_flag_count,
            }
        except Exception:
            return None

    table_name = entity_table_name(entity.type)
    if not table_name or not entity.id:
        return None

    try:
        rows = get_supabase_client().table(table_name).select("*").eq("id", entity.id).limit(1).execute().data or []
    except Exception:
        return None
    if not rows:
        return None

    row = rows[0]
    return {key: value for key, value in row.items() if key in {"id", "title", "status", "merchant", "amount_cad", "transaction_id", "queue_status", "review_level", "extraction_status", "report_name"}}


def entity_table_name(entity_type: str) -> str | None:
    return {
        "transaction_row": "transactions",
        "review_queue_item": "review_queue_items",
        "approval_request": "approval_requests",
        "policy_document": "policy_documents",
    }.get(entity_type)


def extract_recent_results(history: list[InsightChatMessage]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for message in reversed(history):
        if message.role != "assistant":
            continue
        metadata = message.metadata if isinstance(message.metadata, dict) else {}
        if metadata.get("kind") != "insight_response":
            continue
        results.append(
            {
                "question": metadata.get("question"),
                "summary": metadata.get("summary") or message.content,
                "planner_source": metadata.get("planner_source"),
                "tool": (metadata.get("plan") or {}).get("tool") if isinstance(metadata.get("plan"), dict) else None,
                "visualization": metadata.get("visualization"),
                "analysis_frame": metadata.get("analysis_frame"),
            }
        )
        if len(results) >= RECENT_RESULT_LIMIT:
            break
    return list(reversed(results))


def extract_recent_artifacts(history: list[InsightChatMessage]) -> list[AskContextArtifact]:
    artifacts: list[AskContextArtifact] = []
    for message in reversed(history):
        if message.role != "assistant":
            continue
        metadata = message.metadata if isinstance(message.metadata, dict) else {}
        if metadata.get("kind") != "insight_response":
            continue
        tool_name = (metadata.get("plan") or {}).get("tool") if isinstance(metadata.get("plan"), dict) else None
        artifacts.extend(
            [
                AskContextArtifact(type="brief", label=f"{tool_name or 'insight'} brief", status="available"),
                AskContextArtifact(type="csv", label=f"{tool_name or 'insight'} csv", status="available"),
                AskContextArtifact(type="diagram", label=f"{tool_name or 'insight'} diagram", status="available"),
            ]
        )
        if artifacts:
            break
    return artifacts[:3]


def derive_context_scope(
    *,
    page_context: InsightPageContext | None,
    focus_entities: list[AskContextEntity],
    visible_entities: list[AskContextEntity],
    artifacts: list[AskContextArtifact],
    recent_results: list[dict[str, Any]],
    hydrated_entities: dict[str, Any],
) -> list[str]:
    scope: list[str] = ["global_summaries"]
    if page_context:
        scope.append("page_context")
    if focus_entities or visible_entities:
        scope.append("visible_entities")
    if hydrated_entities:
        scope.append("db_facts")
    if recent_results:
        scope.append("session_memory")
    if artifacts:
        scope.append("page_artifacts")
    return scope


def _summary_row_for_key(summary_key: str, ask_context: AskContextEnvelope) -> InsightResultRow | None:
    summary = ask_context.global_summaries.get(summary_key)
    if summary_key == "reports" and not isinstance(summary, dict):
        summary = {}
    if not isinstance(summary, dict) or (not summary and summary_key != "reports"):
        return None

    if summary_key == "dashboard":
        return InsightResultRow(
            label="Overview",
            values={
                "normalized_transaction_count": summary.get("normalized_transaction_count"),
                "raw_transaction_count": summary.get("raw_transaction_count"),
                "employee_count": summary.get("employee_count"),
                "department_count": summary.get("department_count"),
            },
        )
    if summary_key == "review":
        queue = summary.get("queue") if isinstance(summary.get("queue"), dict) else {}
        policy = summary.get("policy") if isinstance(summary.get("policy"), dict) else {}
        return InsightResultRow(
            label="Review queue",
            values={
                "open_queue_items": queue.get("open"),
                "high_or_critical": queue.get("high_or_critical") or policy.get("high_or_critical"),
                "policy_flagged": queue.get("policy_flagged"),
                "review_required": policy.get("review_required"),
            },
        )
    if summary_key == "approvals":
        return InsightResultRow(
            label="Approvals",
            values={
                "active_approvals": summary.get("active"),
                "decided_approvals": summary.get("decided"),
                "total_approvals": summary.get("total"),
            },
        )
    if summary_key == "reports":
        return InsightResultRow(
            label="Reports",
            values={
                "report_count": summary.get("report_count"),
            },
        )
    if summary_key == "policy_setup":
        latest_document = summary.get("latest_document") if isinstance(summary.get("latest_document"), dict) else {}
        return InsightResultRow(
            label="Policy setup",
            values={
                "rule_count": summary.get("rule_count"),
                "active_rules": summary.get("active_rules"),
                "draft_rules": summary.get("draft_rules"),
                "latest_document": latest_document.get("title"),
            },
        )
    if summary_key == "risk":
        level_counts = summary.get("level_counts") if isinstance(summary.get("level_counts"), dict) else {}
        return InsightResultRow(
            label="Risk",
            values={
                "returned_scores": summary.get("returned_scores"),
                "critical": level_counts.get("critical", 0),
                "high": level_counts.get("high", 0),
                "medium": level_counts.get("medium", 0),
            },
        )
    if summary_key == "transactions":
        return InsightResultRow(
            label="Transactions",
            values={
                "normalized_transaction_count": summary.get("normalized_transaction_count"),
                "department_count": summary.get("department_count"),
            },
        )
    return InsightResultRow(label=summary_key.replace("_", " ").title(), values=summary)
