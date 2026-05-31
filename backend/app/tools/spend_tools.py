from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from app.database.supabase_client import get_supabase_client
from app.schemas.insights import InsightChatMessage, InsightCitation, InsightPlan, InsightResultRow
from app.services.rag_service import retrieve_policy_chunks
from app.services.review_queue_service import list_review_queue, summarize_review_queue

FETCH_BATCH_SIZE = 1000


def execute_insight_tool(
    plan: InsightPlan,
    question: str | None = None,
    history: list[InsightChatMessage] | None = None,
) -> tuple[list[InsightResultRow], dict[str, Any], list[InsightCitation]]:
    citations: list[InsightCitation] = []

    if plan.tool == "review.currentQueue":
        queue_items = _filtered_review_queue_items(plan.filters)
        rows = _review_queue_rows(queue_items, plan.metrics)
        summary = summarize_review_queue(queue_items)
        metadata = {
            "record_count": len(queue_items),
            "returned_count": min(len(rows), plan.limit),
            "queue_total": summary.total,
            "queue_open": summary.open,
            "queue_critical": sum(1 for item in queue_items if item.review_level == "critical"),
            "queue_high": sum(1 for item in queue_items if item.review_level == "high"),
            "queue_policy_flagged": summary.policy_flagged,
            "queue_risk_flagged": summary.risk_flagged,
        }
        rows = _sort_rows(rows, plan.sort)
        limited_rows = rows[: plan.limit]
        return limited_rows, metadata, citations

    records = _load_enriched_transactions()
    filtered = [_record for _record in records if _matches_filters(_record, plan.filters)]

    if plan.tool == "spend.summary":
        rows = [_summary_row("All matching spend", filtered, plan.metrics)]
    elif plan.tool == "spend.groupBy":
        dimension = plan.group_by[0] if plan.group_by else "department"
        rows = _group_rows(filtered, dimension, plan.metrics)
    elif plan.tool == "spend.compare":
        comparison_targets = [str(target) for target in plan.comparison_options.get("targets") or []]
        comparison_dimension = str(plan.comparison_options.get("dimension") or "department")
        focus_dimension = plan.group_by[0] if plan.group_by else str(plan.comparison_options.get("focus_dimension") or "department")
        rows = _comparison_rows(filtered, focus_dimension, comparison_dimension, comparison_targets, plan.metrics)
    elif plan.tool == "spend.topMerchants":
        rows = _group_rows(filtered, "merchant", plan.metrics)
    elif plan.tool == "spend.topTransactions":
        rows = _top_transaction_rows(filtered, plan.metrics)
    elif plan.tool == "policy.latestFindings":
        policy_records = [record for record in filtered if _is_policy_flag(record)]
        dimension = plan.group_by[0] if plan.group_by else "department"
        rows = _group_rows(policy_records, dimension, plan.metrics or ["policy_flag_count", "sum_amount_cad"])
    elif plan.tool == "risk.latestSignals":
        risk_records = [record for record in filtered if _is_risk_flag(record)]
        rows = _transaction_rows(risk_records, plan.metrics)
    elif plan.tool == "policy.retrieveClauses":
        retrieval = retrieve_policy_chunks(query=_policy_query_text(question, history))
        citations = [
            InsightCitation(
                rule_code=chunk.rule_code,
                clause_id=chunk.id,
                title=str(chunk.citation.get("section_label") or chunk.citation.get("title") or chunk.rule_code or "Policy clause"),
                text=chunk.content,
                source=str(chunk.citation.get("document_id") or chunk.document_id or ""),
                match_score=chunk.similarity,
            )
            for chunk in retrieval.chunks
        ]
        rows = _policy_clause_rows(citations)
    else:
        rows = []

    rows = _sort_rows(rows, plan.sort)
    limited_rows = rows[: plan.limit]
    return limited_rows, {"record_count": len(filtered), "returned_count": len(limited_rows), "total_groups": len(rows)}, citations


def _load_enriched_transactions() -> list[dict[str, Any]]:
    transactions = _fetch_all("transactions", "*", "created_at")
    employees = {row["id"]: row for row in _fetch_all("employees", "id, full_name, department_id", "created_at") if row.get("id")}
    departments = {row["id"]: row for row in _fetch_all("departments", "id, name", "created_at") if row.get("id")}
    checks = _latest_by_transaction_id(_fetch_all("policy_checks", "*", "created_at"))
    risks = _latest_by_transaction_id(_fetch_all("risk_scores", "*", "created_at"))

    records = []
    for transaction in transactions:
        employee = employees.get(transaction.get("employee_id") or "")
        department = departments.get(transaction.get("department_id") or "")
        check = checks.get(transaction.get("id") or "")
        risk = risks.get(transaction.get("id") or "")
        merchant = transaction.get("normalized_merchant_name") or transaction.get("merchant_name") or "Unknown merchant"
        category = transaction.get("business_category") or transaction.get("normalized_category") or "Uncategorized"
        records.append(
            {
                **transaction,
                "employee": employee.get("full_name") if employee else None,
                "department": department.get("name") if department else None,
                "merchant": merchant,
                "business_category": category,
                "policy_status": check.get("status") if check else "not_scanned",
                "policy_severity": check.get("max_severity") if check else None,
                "risk_level": risk.get("risk_level") if risk else "none",
                "risk_score": float(risk.get("risk_score") or 0) if risk else 0,
            }
        )
    return records


def _fetch_all(table_name: str, columns: str, order_column: str) -> list[dict[str, Any]]:
    client = get_supabase_client()
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        batch = (
            client.table(table_name)
            .select(columns)
            .order(order_column)
            .range(start, start + FETCH_BATCH_SIZE - 1)
            .execute()
            .data
            or []
        )
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < FETCH_BATCH_SIZE:
            break
        start += FETCH_BATCH_SIZE
    return rows


def _latest_by_transaction_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        transaction_id = row.get("transaction_id")
        if not transaction_id:
            continue
        current = latest.get(str(transaction_id))
        current_time = str(current.get("created_at") or current.get("checked_at") or current.get("scored_at") or "") if current else ""
        row_time = str(row.get("created_at") or row.get("checked_at") or row.get("scored_at") or "")
        if current is None or row_time >= current_time:
            latest[str(transaction_id)] = row
    return latest


def _matches_filters(record: dict[str, Any], filters: dict[str, Any]) -> bool:
    if not _matches_date_range(record, filters.get("date_start"), filters.get("date_end")):
        return False

    return all(
        [
            _matches_transaction_ids(record.get("id"), filters.get("transaction_ids")),
            _matches_text_or_list(record.get("department"), filters.get("department")),
            _matches_text_or_list(record.get("employee"), filters.get("employee")),
            _contains_text(record.get("merchant"), filters.get("merchant")),
            _matches_text_or_list(record.get("business_category"), filters.get("category")),
            _matches_text_or_list(record.get("policy_status"), filters.get("policy_status")),
            _matches_text_or_list(record.get("risk_level"), filters.get("risk_level")),
            _matches_text_or_list(record.get("debit_credit"), filters.get("debit_credit")),
        ]
    )


def _matches_transaction_ids(value: Any, expected: Any) -> bool:
    if expected in (None, "", []):
        return True
    normalized_value = str(value or "").strip()
    if isinstance(expected, list):
        return normalized_value in {str(item).strip() for item in expected if str(item).strip()}
    return normalized_value == str(expected).strip()


def _matches_date_range(record: dict[str, Any], start: Any, end: Any) -> bool:
    if not start and not end:
        return True
    raw_value = record.get("transaction_date") or record.get("posting_date")
    if not raw_value:
        return False
    value = date.fromisoformat(str(raw_value)[:10])
    if start and value < date.fromisoformat(str(start)[:10]):
        return False
    if end and value > date.fromisoformat(str(end)[:10]):
        return False
    return True


def _matches_text_or_list(value: Any, expected: Any) -> bool:
    if expected in (None, "", []):
        return True
    normalized_value = _normalize(value)
    if isinstance(expected, list):
        return any(normalized_value == _normalize(item) for item in expected)
    return normalized_value == _normalize(expected)


def _contains_text(value: Any, expected: Any) -> bool:
    if expected in (None, ""):
        return True
    return _normalize(expected) in _normalize(value)


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower()


def _group_rows(records: list[dict[str, Any]], dimension: str, metrics: list[str]) -> list[InsightResultRow]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[_dimension_value(record, dimension)].append(record)
    return [_summary_row(label, rows, metrics) for label, rows in grouped.items()]


def _comparison_rows(
    records: list[dict[str, Any]],
    focus_dimension: str,
    comparison_dimension: str,
    comparison_targets: list[str],
    metrics: list[str],
) -> list[InsightResultRow]:
    if not comparison_targets:
        return _group_rows(records, focus_dimension, metrics)

    grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for record in records:
        focus_label = _dimension_value(record, focus_dimension)
        comparison_label = _dimension_value(record, comparison_dimension)
        grouped[focus_label][comparison_label].append(record)

    rows: list[InsightResultRow] = []
    for focus_label, groups in grouped.items():
        values: dict[str, Any] = {}
        total_sum_amount_cad = 0.0
        total_transaction_count = 0

        for target in comparison_targets:
            target_rows = groups.get(target, [])
            target_values = _metric_values(target_rows, metrics)
            target_slug = _slugify_target(target)
            for metric_name, metric_value in target_values.items():
                values[f"{target_slug}_{metric_name}"] = metric_value
            total_sum_amount_cad += float(target_values.get("sum_amount_cad") or 0)
            total_transaction_count += int(target_values.get("transaction_count") or 0)

        if len(comparison_targets) >= 2:
            left_slug = _slugify_target(comparison_targets[0])
            right_slug = _slugify_target(comparison_targets[1])
            values["delta_sum_amount_cad"] = round(
                float(values.get(f"{left_slug}_sum_amount_cad") or 0) - float(values.get(f"{right_slug}_sum_amount_cad") or 0),
                2,
            )
            values["delta_transaction_count"] = int(values.get(f"{left_slug}_transaction_count") or 0) - int(
                values.get(f"{right_slug}_transaction_count") or 0
            )

        values["total_sum_amount_cad"] = round(total_sum_amount_cad, 2)
        values["total_transaction_count"] = total_transaction_count
        rows.append(InsightResultRow(label=focus_label, values=values))

    return rows


def _transaction_rows(records: list[dict[str, Any]], metrics: list[str]) -> list[InsightResultRow]:
    sorted_records = sorted(records, key=lambda record: (float(record.get("risk_score") or 0), abs(float(record.get("amount_cad") or 0))), reverse=True)
    rows = []
    for record in sorted_records:
        rows.append(
            InsightResultRow(
                label=str(record.get("merchant") or record.get("id") or "Transaction"),
                values={
                    "employee": record.get("employee") or "Unassigned",
                    "department": record.get("department") or "Unassigned",
                    "amount_cad": round(float(record.get("amount_cad") or 0), 2),
                    "risk_level": record.get("risk_level") or "none",
                    "risk_score": round(float(record.get("risk_score") or 0), 2),
                    "transaction_date": record.get("transaction_date") or record.get("posting_date"),
                    **_metric_values([record], metrics),
                },
            )
        )
    return rows


def _top_transaction_rows(records: list[dict[str, Any]], metrics: list[str]) -> list[InsightResultRow]:
    sorted_records = sorted(records, key=lambda record: abs(float(record.get("amount_cad") or 0)), reverse=True)
    rows: list[InsightResultRow] = []
    for record in sorted_records:
        amount_cad = round(float(record.get("amount_cad") or 0), 2)
        merchant = str(record.get("merchant") or record.get("normalized_merchant_name") or record.get("merchant_name") or record.get("id") or "Transaction")
        rows.append(
            InsightResultRow(
                label=merchant,
                values={
                    "transaction_id": record.get("id"),
                    "employee": record.get("employee") or "Unassigned",
                    "department": record.get("department") or "Unassigned",
                    "merchant": merchant,
                    "business_category": record.get("business_category") or "Uncategorized",
                    "amount_cad": amount_cad,
                    "sum_amount_cad": amount_cad,
                    "transaction_count": 1,
                    "avg_amount_cad": amount_cad,
                    "transaction_date": record.get("transaction_date") or record.get("posting_date"),
                    **_metric_values([record], metrics),
                },
            )
        )
    return rows


def _summary_row(label: str, records: list[dict[str, Any]], metrics: list[str]) -> InsightResultRow:
    return InsightResultRow(label=label, values=_metric_values(records, metrics))


def _policy_clause_rows(citations: list[InsightCitation]) -> list[InsightResultRow]:
    return [
        InsightResultRow(
            label=citation.title or citation.rule_code or "Policy clause",
            values={
                "rule_code": citation.rule_code,
                "text": citation.text,
                "source": citation.source,
                "match_score": round(float(citation.match_score or 0), 3) if citation.match_score is not None else None,
            },
        )
        for citation in citations
    ]


def _filtered_review_queue_items(filters: dict[str, Any]) -> list[Any]:
    queue_status = filters.get("queue_status")
    review_level = filters.get("review_level")
    policy_status = filters.get("policy_status")
    items = list_review_queue(
        limit=500,
        queue_status=str(queue_status) if queue_status not in (None, "", []) else "",
        review_level=str(review_level) if review_level else None,
        policy_status=str(policy_status) if policy_status else None,
    )

    return [
        item
        for item in items
        if all(
            [
                _matches_text_or_list(item.department, filters.get("department")),
                _matches_text_or_list(item.employee, filters.get("employee")),
                _contains_text(item.merchant, filters.get("merchant")),
                _matches_text_or_list(item.category, filters.get("category")),
                _matches_text_or_list(item.risk_level, filters.get("risk_level")),
            ]
        )
    ]


def _review_queue_rows(items: list[Any], metrics: list[str]) -> list[InsightResultRow]:
    rows: list[InsightResultRow] = []
    for item in items:
        policy_reasons = [
            str(flag.get("explanation") or flag.get("required_action") or flag.get("rule_code") or "policy concern")
            for flag in item.policy_flags[:2]
            if isinstance(flag, dict)
        ]
        risk_reasons = [signal.message for signal in item.risk_signals[:2]]
        reason_parts = [part.strip() for part in [*policy_reasons, *risk_reasons] if part and str(part).strip()]
        reviewer_summary = item.reviewer_brief.summary if item.reviewer_brief else None
        rows.append(
            InsightResultRow(
                label=str(item.merchant or item.transaction_id),
                values={
                    "transaction_id": item.transaction_id,
                    "employee": item.employee or "Unassigned",
                    "department": item.department or "Unassigned",
                    "amount_cad": round(float(item.amount_cad or 0), 2),
                    "category": item.category,
                    "queue_status": item.queue_status,
                    "review_level": item.review_level,
                    "review_priority": item.review_priority,
                    "policy_status": item.policy_status or "unknown",
                    "risk_level": item.risk_level or "none",
                    "risk_score": item.risk_score,
                    "policy_flag_count": len(item.policy_flags),
                    "risk_signal_count": len(item.risk_signals),
                    "transaction_date": item.transaction_date,
                    "next_action": item.next_action,
                    "reason_summary": "; ".join(reason_parts[:3]) if reason_parts else (reviewer_summary or item.ai_context or item.next_action),
                    "reviewer_summary": reviewer_summary or item.ai_context or item.next_action,
                    **_metric_values(
                        [
                            {
                                "amount_cad": item.amount_cad,
                                "policy_status": item.policy_status,
                                "risk_level": item.risk_level,
                            }
                        ],
                        metrics,
                    ),
                },
            )
        )
    return rows


def _metric_values(records: list[dict[str, Any]], metrics: list[str]) -> dict[str, Any]:
    amounts = [float(record.get("amount_cad") or 0) for record in records]
    values: dict[str, Any] = {}
    for metric in metrics:
        if metric == "sum_amount_cad":
            values[metric] = round(sum(amounts), 2)
        elif metric == "amount_cad":
            values[metric] = round(sum(amounts), 2)
        elif metric == "transaction_count":
            values[metric] = len(records)
        elif metric == "avg_amount_cad":
            values[metric] = round(sum(amounts) / len(amounts), 2) if amounts else 0
        elif metric == "policy_flag_count":
            values[metric] = sum(1 for record in records if _is_policy_flag(record))
        elif metric == "risk_flag_count":
            values[metric] = sum(1 for record in records if _is_risk_flag(record))
        elif metric == "missing_receipt_count":
            values[metric] = 0
        elif metric == "missing_preapproval_count":
            values[metric] = sum(1 for record in records if record.get("policy_status") == "approval_evidence_needed")
    return values


def _dimension_value(record: dict[str, Any], dimension: str) -> str:
    if dimension == "merchant":
        return str(record.get("merchant") or "Unknown merchant")
    if dimension == "employee":
        return str(record.get("employee") or "Unassigned")
    if dimension == "department":
        return str(record.get("department") or "Unassigned")
    if dimension in {"business_category", "normalized_category"}:
        return str(record.get("business_category") or record.get("normalized_category") or "Uncategorized")
    if dimension == "month":
        raw_date = str(record.get("transaction_date") or record.get("posting_date") or "")
        return raw_date[:7] if len(raw_date) >= 7 else "Unknown month"
    if dimension == "policy_status":
        return str(record.get("policy_status") or "not_scanned")
    if dimension == "risk_level":
        return str(record.get("risk_level") or "none")
    return "Other"


def _is_policy_flag(record: dict[str, Any]) -> bool:
    return record.get("policy_status") not in {None, "compliant", "excluded_non_expense", "not_scanned"}


def _is_risk_flag(record: dict[str, Any]) -> bool:
    risk_level = str(record.get("risk_level") or "").lower()
    return risk_level in {"medium", "high", "critical"} or float(record.get("risk_score") or 0) >= 60


def _sort_rows(rows: list[InsightResultRow], sort: list[dict[str, Any]]) -> list[InsightResultRow]:
    if not sort:
        return sorted(
            rows,
            key=lambda row: float(
                row.values.get("total_sum_amount_cad")
                or row.values.get("sum_amount_cad")
                or row.values.get("risk_score")
                or row.values.get("transaction_count")
                or 0
            ),
            reverse=True,
        )
    sort_spec = sort[0]
    field = str(sort_spec.get("field") or "sum_amount_cad")
    descending = str(sort_spec.get("direction") or "desc").lower() != "asc"
    return sorted(rows, key=lambda row: _sort_key_for_row(row, field), reverse=descending)


def _sort_key_for_row(row: InsightResultRow, field: str) -> Any:
    if field in row.values:
        return row.values.get(field) or 0
    if field in {"label", "month", "department", "employee", "merchant", "business_category", "normalized_category", "policy_status", "risk_level"}:
        return row.label
    return row.values.get(field) or 0


def _policy_query_text(question: str | None, history: list[InsightChatMessage] | None) -> str:
    if question and question.strip():
        return question.strip()
    if history:
        for message in reversed(history):
            if message.role == "user" and message.content.strip():
                return message.content.strip()
    return "Policy explanation"


def _slugify_target(value: str) -> str:
    return "_".join(part for part in str(value or "").strip().lower().replace("&", "and").split() if part)
