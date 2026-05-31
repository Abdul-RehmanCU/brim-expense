from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
from collections.abc import Callable
from functools import lru_cache
from time import perf_counter
from typing import Any
from uuid import uuid4

from app.config import get_settings
from app.database.supabase_client import get_supabase_client
from app.schemas.policy import (
    ExtractedDraftRule,
    PolicyCheckResult,
    PolicyDocumentCreateResponse,
    PolicyDocumentExtractRequest,
    PolicyDocumentItem,
    PolicyDocumentTextRequest,
    PolicyFindingItem,
    PolicyExtractionRunItem,
    PolicyRuleExtractionRequest,
    PolicyRuleExtractionResponse,
    PolicyRuleItem,
    PolicyRulePatchRequest,
    PolicyRuleStatus,
    PolicyRuleTestRequest,
    PolicyRuleTestResponse,
    PolicyRuleWriteRequest,
    PolicyResetResponse,
    PolicyScanRequest,
    PolicyScanSummary,
    PolicyStatus,
    PolicyViolation,
    RepeatOffenderItem,
    RepeatOffenderSummary,
    Severity,
    ViolationListItem,
)
from app.services.ai_service import JsonCompletionClient, extract_policy_rules_json
from app.services.rag_service import PolicyRagIngestionResult, ingest_policy_document_chunks
from app.services.policy_engine import (
    ENGINE_VERSION,
    build_policy_context,
    evaluate_policy,
    infer_synthetic_preapproval,
    infer_synthetic_receipt,
    infer_policy_category,
    policy_thresholds_from_rules,
    utc_now_iso,
)
from app.services.rule_evaluator import (
    ALLOWED_CONTEXT_FIELDS,
    ConfigurablePolicyRule,
    RuleValidationError,
    evaluate_configurable_rule,
    normalize_outcome_status,
    validate_configurable_rule,
)

PAGE_SIZE = 500
POLICY_CLEAR_STATUSES = {"compliant", "excluded_non_expense", None}
POLICY_DOCUMENTS_BUCKET = "policy-documents"
POLICY_TEXT_PREVIEW_CHARS = 600
POLICY_TEXT_EXTRACTION_LIMIT = 60000
ALLOWED_RULE_OPERATORS = {
    "equals",
    "not_equals",
    "in",
    "not_in",
    "greater_than",
    "greater_than_or_equal",
    "less_than",
    "less_than_or_equal",
    "contains",
    "not_contains",
    "exists",
    "missing",
    "between",
}
LEGACY_OPERATOR_MAP = {
    "equals": "eq",
    "not_equals": "neq",
    "greater_than": "gt",
    "greater_than_or_equal": "gte",
    "less_than": "lt",
    "less_than_or_equal": "lte",
    "missing": "exists",
}
ALLOWED_RULE_LOGIC_KEYS = {"all", "any", "not"}
ALLOWED_RULE_FIELDS = {
    "amount_cad",
    "merchant_raw",
    "merchant_normalized",
    "normalized_merchant_family",
    "transaction_code",
    "transaction_type",
    "transaction_eligibility",
    "network_category_code",
    "business_category",
    "normalized_category",
    "policy_category",
    "department_id",
    "department_name",
    "employee_id",
    "employee_name",
    "employee_role",
    "transaction_date",
    "posting_date",
    "posting_delay_days",
    "merchant_country",
    "merchant_state_province",
    "merchant_postal_code",
    "mcc",
    "mcc_description",
    "debit_or_credit",
    "category_confidence",
    "category_source",
    "is_foreign_transaction",
    "is_weekend",
    "is_account_activity",
    "is_credit_or_refund",
    "is_low_confidence_category",
    "is_uncategorized",
}
BROAD_ACTIVITY_FIELDS = {
    "debit_credit",
    "debit_or_credit",
    "is_account_activity",
    "is_credit_or_refund",
    "transaction_eligibility",
    "transaction_type",
}
CATEGORY_OR_MERCHANT_FIELDS = {
    "business_category",
    "category",
    "is_alcohol_category",
    "is_meal_or_entertainment",
    "is_personal_expense",
    "is_ticket_or_fine",
    "mcc",
    "mcc_description",
    "merchant_normalized",
    "merchant_raw",
    "network_category_code",
    "normalized_category",
    "normalized_merchant_family",
    "policy_category",
    "receipt_sensitive_category",
    "search_text",
}
EVIDENCE_FIELDS = {
    "has_business_purpose",
    "has_guest_names",
    "has_pending_preapproval",
    "has_receipt_evidence",
    "missing_preapproval",
    "preapproval_status",
    "receipt_evidence_unavailable",
    "receipt_explicitly_missing",
    "receipt_status",
    "receipt_submitted_current_month",
    "requires_preapproval",
}
HUMAN_JUDGMENT_TERMS = {
    "abuse",
    "actually incurred",
    "business purpose",
    "cardholder",
    "falsif",
    "good judgment",
    "named individual",
    "personal use",
    "reasonable",
}
SEVERITY_RANK: dict[Severity, int] = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


def check_transaction_policy(transaction_id: str, reset_synthetic_evidence: bool = False) -> PolicyCheckResult:
    transaction = fetch_transaction(transaction_id)
    if not transaction:
        raise ValueError(f"Transaction {transaction_id} was not found.")

    transaction = enrich_transactions_with_people([transaction])[0]
    active_configurable_rules = load_active_configurable_rules()
    receipt = get_or_create_receipt(transaction, reset_synthetic_evidence)
    preapproval = get_or_create_preapproval(
        transaction,
        reset_synthetic_evidence,
        thresholds=policy_thresholds_from_rules(active_configurable_rules, transaction),
    )
    result = evaluate_policy_with_configurable_rules(
        transaction,
        receipt,
        preapproval,
        active_configurable_rules,
    )
    persist_policy_result(result)
    return result


def scan_transactions(request: PolicyScanRequest | None = None) -> PolicyScanSummary:
    request = request or PolicyScanRequest()
    started_at = perf_counter()
    batch_size = normalized_batch_size(request.batch_size)
    summary = PolicyScanSummary()
    active_configurable_rules = load_active_configurable_rules()

    for transactions in iter_transaction_batches(request, batch_size):
        if not transactions:
            continue

        summary.batch_count += 1
        transactions = enrich_transactions_with_people(transactions)
        transaction_ids = [transaction["id"] for transaction in transactions]
        receipts_by_transaction_id = resolve_receipts(
            transactions,
            request.reset_synthetic_evidence,
            request.dry_run,
        )
        preapprovals_by_transaction_id = resolve_preapprovals(
            transactions,
            request.reset_synthetic_evidence,
            request.dry_run,
            active_configurable_rules,
        )
        results: list[PolicyCheckResult] = []

        for transaction in transactions:
            receipt = receipts_by_transaction_id.get(transaction["id"])
            preapproval = preapprovals_by_transaction_id.get(transaction["id"])
            result = evaluate_policy_with_configurable_rules(
                transaction,
                receipt,
                preapproval,
                active_configurable_rules,
            )
            apply_result_to_summary(summary, result)
            results.append(result)

        if not request.dry_run:
            persist_policy_results(results, transaction_ids, reset_existing=request.reset_existing)

    summary.duration_ms = int((perf_counter() - started_at) * 1000)
    return summary


def run_policy_scan_and_refresh(request: PolicyScanRequest | None = None) -> PolicyScanSummary:
    request = request or PolicyScanRequest()
    summary = scan_transactions(request)
    if request.dry_run:
        return summary

    try:
        from app.schemas.risk import RiskScanRequest
        from app.services.risk_service import scan_risk_scores

        scan_risk_scores(
            RiskScanRequest(
                employee_id=request.employee_id,
                department_id=request.department_id,
                date_start=request.date_start,
                date_end=request.date_end,
                limit=request.limit,
                reset_existing=False,
            )
        )
    except Exception:
        pass

    try:
        from app.schemas.review_queue import ReviewQueueRefreshRequest
        from app.services.review_queue_service import (
            refresh_review_queue,
            refresh_review_queue_for_transaction_ids,
        )

        transaction_ids: list[str] = []
        for batch in iter_transaction_batches(request, normalized_batch_size(request.batch_size)):
            transaction_ids.extend(
                str(transaction["id"])
                for transaction in batch
                if transaction.get("id")
            )

        unique_transaction_ids = unique_ids(transaction_ids)
        if unique_transaction_ids:
            refresh_review_queue_for_transaction_ids(unique_transaction_ids, persist=True)
        else:
            refresh_review_queue(
                ReviewQueueRefreshRequest(
                    limit=request.limit,
                    persist=True,
                    reset_existing=False,
                )
            )
    except Exception:
        pass

    return summary


def get_policy_summary() -> PolicyScanSummary:
    client = get_supabase_client()
    checks: list[dict[str, Any]] = []
    start = 0
    while True:
        batch = (
            client.table("policy_checks")
            .select("status,max_severity")
            .range(start, start + PAGE_SIZE - 1)
            .execute()
            .data
            or []
        )
        checks.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        start += PAGE_SIZE

    violations_count = count_table("violations")
    summary = PolicyScanSummary(violations_created=violations_count, individual_flags=violations_count)

    for check in checks:
        status = check.get("status")
        if status in {
            "compliant",
            "excluded_non_expense",
            "approval_evidence_needed",
            "context_needed",
            "policy_violation",
            "review_required",
        }:
            summary.total_scanned += 1
            setattr(summary, status, getattr(summary, status) + 1)
            if status == "approval_evidence_needed":
                summary.approval_evidence_required += 1
            if status == "policy_violation":
                summary.policy_violations += 1
        if check.get("max_severity") in {"high", "critical"}:
            summary.high_or_critical += 1

    summary.evidence_required = count_evidence_required_transactions()

    return summary


def list_violations(
    severity: str | None = None,
    status: str | None = None,
    department_id: str | None = None,
    limit: int = 250,
) -> list[ViolationListItem]:
    client = get_supabase_client()
    query = client.table("violations").select("*").order("created_at", desc=True).limit(limit)
    if severity:
        query = query.eq("severity", severity)

    violations = query.execute().data or []
    if not violations:
        return []

    check_ids = unique_ids(violation.get("policy_check_id") for violation in violations)
    transaction_ids = unique_ids(violation.get("transaction_id") for violation in violations)

    checks = fetch_by_ids("policy_checks", check_ids)
    checks_by_id = {check["id"]: check for check in checks}
    transactions = fetch_by_ids("transactions", transaction_ids)
    transactions_by_id = {transaction["id"]: transaction for transaction in transactions}

    employee_ids = unique_ids(transaction.get("employee_id") for transaction in transactions)
    department_ids = unique_ids(transaction.get("department_id") for transaction in transactions)
    employees_by_id = {employee["id"]: employee for employee in fetch_by_ids("employees", employee_ids)}
    departments_by_id = {department["id"]: department for department in fetch_by_ids("departments", department_ids)}

    items: list[ViolationListItem] = []
    for violation in violations:
        check = checks_by_id.get(violation["policy_check_id"])
        transaction = transactions_by_id.get(violation["transaction_id"])
        if not check or not transaction:
            continue
        if status and check.get("status") != status:
            continue
        if department_id and transaction.get("department_id") != department_id:
            continue

        employee = employees_by_id.get(transaction.get("employee_id") or "")
        department = departments_by_id.get(transaction.get("department_id") or "")
        merchant = transaction.get("normalized_merchant_name") or transaction.get("merchant_name")

        items.append(
            ViolationListItem(
                id=violation["id"],
                transaction_id=violation["transaction_id"],
                policy_check_id=violation["policy_check_id"],
                rule_code=violation["rule_code"],
                status=check["status"],
                severity=violation["severity"],
                explanation=violation["explanation"],
                required_action=violation["required_action"],
                transaction_date=transaction.get("transaction_date"),
                merchant=merchant,
                amount_cad=float(transaction.get("amount_cad") or 0),
                category=transaction.get("business_category") or transaction.get("normalized_category") or "Uncategorized",
                employee=employee.get("full_name") if employee else None,
                department=department.get("name") if department else None,
            )
        )

    return items


def list_findings(
    severity: str | None = None,
    status: str | None = None,
    department_id: str | None = None,
    limit: int = 250,
) -> list[PolicyFindingItem]:
    checks = fetch_policy_checks(severity=severity, status=status)
    if not checks:
        return []

    transaction_ids = unique_ids(check.get("transaction_id") for check in checks)
    transactions = fetch_by_ids("transactions", transaction_ids)
    if department_id:
        transactions = [transaction for transaction in transactions if transaction.get("department_id") == department_id]

    filtered_transaction_ids = {transaction["id"] for transaction in transactions}
    checks = [check for check in checks if check.get("transaction_id") in filtered_transaction_ids]
    violations = fetch_by_transaction_ids("violations", list(filtered_transaction_ids))

    employee_ids = unique_ids(transaction.get("employee_id") for transaction in transactions)
    department_ids = unique_ids(transaction.get("department_id") for transaction in transactions)
    employees = fetch_by_ids("employees", employee_ids)
    departments = fetch_by_ids("departments", department_ids)

    findings = compose_policy_findings(checks, violations, transactions, employees, departments)
    return sorted(
        findings,
        key=lambda finding: (
            SEVERITY_RANK[finding.max_severity],
            finding.severity_score,
            finding.amount_cad,
            finding.date or "",
        ),
        reverse=True,
    )[:limit]


def get_repeat_offender_summary(limit: int = 5) -> RepeatOffenderSummary:
    review_rows = fetch_open_review_queue_policy_flags()
    if review_rows:
        employees = fetch_by_ids("employees", unique_ids(row.get("employee_id") for row in review_rows))
        departments = fetch_by_ids("departments", unique_ids(row.get("department_id") for row in review_rows))
        return compose_repeat_offender_summary_from_review_queue(review_rows, employees, departments, limit)

    violations = fetch_open_violations()
    if not violations:
        return RepeatOffenderSummary()

    transaction_ids = unique_ids(violation.get("transaction_id") for violation in violations)
    transactions = fetch_by_ids("transactions", transaction_ids)
    employees = fetch_by_ids("employees", unique_ids(transaction.get("employee_id") for transaction in transactions))
    departments = fetch_by_ids("departments", unique_ids(transaction.get("department_id") for transaction in transactions))
    return compose_repeat_offender_summary(violations, transactions, employees, departments, limit)


def create_policy_document_from_text(request: PolicyDocumentTextRequest) -> PolicyDocumentCreateResponse:
    policy_text = normalize_policy_document_text(request.policy_text)
    document_id = str(uuid4())
    payload = {
        "id": document_id,
        "title": request.title.strip(),
        "version": generated_policy_document_version("text"),
        "source_type": "pasted_text",
        "content": policy_text,
        "raw_text": policy_text,
        "extracted_text": policy_text,
        "extraction_status": "extracted",
        "extraction_error": None,
        "synthetic": False,
        "active": True,
    }
    rows = get_supabase_client().table("policy_documents").insert(payload).execute().data or []
    row = rows[0] if rows else payload
    rag_result = ingest_policy_document_for_rag(row)
    return policy_document_create_response_from_row(row, rag_result)


def upload_policy_document_pdf(
    title: str | None,
    file_name: str,
    content_type: str | None,
    file_bytes: bytes,
) -> PolicyDocumentCreateResponse:
    safe_file_name = sanitized_policy_file_name(file_name)
    if not safe_file_name.lower().endswith(".pdf") and content_type != "application/pdf":
        raise ValueError("Only PDF uploads are supported for policy document ingestion.")
    if not file_bytes:
        raise ValueError("Uploaded PDF was empty.")

    document_id = str(uuid4())
    storage_path = upload_policy_document_bytes(document_id, safe_file_name, file_bytes)
    extracted_text = extract_text_from_pdf_bytes(file_bytes)
    extraction_error = None
    extraction_status = "extracted"
    content = extracted_text
    raw_text = extracted_text or None
    normalized_title = title.strip() if title and title.strip() else policy_document_title_from_file_name(safe_file_name)

    if not extracted_text:
        extraction_status = "failed"
        extraction_error = (
            "This PDF appears scanned or image-based. OCR/Docling support can be added later."
        )
        content = ""
        raw_text = None

    payload = {
        "id": document_id,
        "title": normalized_title,
        "version": generated_policy_document_version("pdf"),
        "source_type": "uploaded_pdf",
        "file_name": safe_file_name,
        "storage_path": storage_path,
        "content": content,
        "raw_text": raw_text,
        "extracted_text": extracted_text or None,
        "extraction_status": extraction_status,
        "extraction_error": extraction_error,
        "synthetic": False,
        "active": True,
    }
    rows = get_supabase_client().table("policy_documents").insert(payload).execute().data or []
    row = rows[0] if rows else payload
    rag_result = ingest_policy_document_for_rag(row)
    return policy_document_create_response_from_row(row, rag_result)


def clear_policy_data() -> PolicyResetResponse:
    warnings: list[str] = []
    rows_deleted: dict[str, int] = {}
    document_rows = fetch_rows_for_reset("policy_documents", "id,storage_path", warnings)
    storage_paths = [str(row.get("storage_path")) for row in document_rows if row.get("storage_path")]

    for table_name in (
        "violations",
        "policy_checks",
        "policy_rules",
        "policy_chunks",
        "policy_extraction_runs",
        "policy_documents",
    ):
        rows_deleted[table_name] = delete_rows_for_reset(table_name, warnings)

    rows_deleted["receipts"] = delete_rows_by_boolean_flag("receipts", "synthetic", True, warnings)
    rows_deleted["preapprovals"] = delete_rows_by_boolean_flag("preapprovals", "synthetic", True, warnings)

    storage_paths_removed = remove_policy_storage_paths(storage_paths, warnings)
    policy_rule_ids_by_code.cache_clear()
    return PolicyResetResponse(
        rows_deleted=rows_deleted,
        storage_paths_removed=storage_paths_removed,
        warnings=warnings,
    )


def extract_policy_rules_for_document(
    policy_document_id: str,
    request: PolicyDocumentExtractRequest | None = None,
    ai_client: JsonCompletionClient | None = None,
) -> PolicyRuleExtractionResponse:
    document = get_policy_document(policy_document_id)
    if not document:
        raise ValueError(f"Policy document {policy_document_id} was not found.")

    policy_text = normalize_policy_document_text(
        str(document.get("extracted_text") or document.get("raw_text") or document.get("content") or "")
    )
    if not policy_text:
        raise ValueError(
            str(
                document.get("extraction_error")
                or "This policy document does not have extractable text yet."
            )
        )

    prepared_text, truncation_warning = prepared_policy_text_for_extraction(policy_text)
    extract_request = PolicyRuleExtractionRequest(
        policy_text=prepared_text,
        company_context=(request.company_context if request else None),
        available_fields=(request.available_fields if request and request.available_fields else available_policy_fields()),
    )
    extraction_run = create_policy_extraction_run(policy_document_id)

    try:
        response = extract_policy_rules(
            extract_request,
            ai_client=ai_client,
            policy_document_id=policy_document_id,
            policy_extraction_run_id=extraction_run.id,
        )
        unsupported = list(response.unsupported_or_missing_fields)
        if truncation_warning:
            unsupported.append(truncation_warning)

        completed_run = update_policy_extraction_run(
            extraction_run.id,
            {
                "status": "completed",
                "summary": response.summary,
                "ambiguities": response.ambiguities,
                "unsupported_or_missing_fields": unsupported,
                "suggested_feature_engineering": response.suggested_feature_engineering,
                "draft_rule_count": len(response.draft_rules),
                "error": None,
            },
        )
        clear_policy_document_extraction_error(policy_document_id)
        return response.model_copy(
            update={
                "policy_document_id": policy_document_id,
                "extraction_run": completed_run,
                "unsupported_or_missing_fields": unsupported,
            }
        )
    except Exception as error:
        update_policy_extraction_run(
            extraction_run.id,
            {
                "status": "failed",
                "summary": None,
                "ambiguities": [],
                "unsupported_or_missing_fields": [],
                "suggested_feature_engineering": [],
                "draft_rule_count": 0,
                "error": str(error),
            },
        )
        raise


def list_policy_rules(limit: int = 50, offset: int = 0, status: str | None = None) -> list[PolicyRuleItem]:
    query = (
        get_supabase_client()
        .table("policy_rules")
        .select("*")
        .order("active", desc=True)
        .order("rule_code")
        .range(offset, offset + limit - 1)
    )
    if status:
        query = query.eq("status", status)
    rows = query.execute().data or []
    return [policy_rule_item_from_row(row) for row in rows]


def create_policy_rule(request: PolicyRuleWriteRequest) -> PolicyRuleItem:
    canonical_rule_json, validation_errors = canonicalize_rule_json(
        request.rule_json,
        request.rule_code,
        request.name,
        request.severity,
    )
    activation_errors = activation_guardrail_errors(canonical_rule_json)
    save_errors = validation_errors + (
        activation_errors if request.status == "active" and request.enabled else []
    )
    payload = {
        "rule_code": request.rule_code.strip().upper(),
        "title": request.name.strip(),
        "name": request.name.strip(),
        "description": request.description.strip(),
        "severity": request.severity,
        "deterministic": True,
        "active": request.status == "active" and request.enabled and not save_errors,
        "enabled": request.status == "active" and request.enabled and not save_errors,
        "status": request.status if not save_errors else "draft",
        "rule_kind": "json_config",
        "condition": canonical_rule_json.get("condition") or {},
        "outcome": canonical_rule_json.get("outcome") or {},
        "scope": canonical_rule_json.get("scope") or {},
        "rule_json": canonical_rule_json,
        "conditions_json": canonical_rule_json.get("condition") or {},
        "outcome_json": canonical_rule_json.get("outcome") or {},
        "scope_json": canonical_rule_json.get("scope") or {},
        "applies_to_json": canonical_rule_json.get("applies_to") or {},
        "thresholds_json": canonical_rule_json.get("thresholds") or {},
        "context_requirements_json": canonical_rule_json.get("context_requirements") or [],
        "requires_json": canonical_rule_json.get("requires") or {},
        "source_type": request.source_type,
        "source_text": request.source_text,
        "validation_errors": save_errors,
        "needs_human_review": False,
        "synthetic": False,
    }
    rows = execute_policy_rules_write_with_schema_fallback(
        lambda sanitized_payload: get_supabase_client().table("policy_rules").insert(sanitized_payload).execute().data or [],
        payload,
    )
    row = rows[0] if rows else payload
    return policy_rule_item_from_row(row, canonical_rule_json, save_errors, request.source_type, request.source_text)


def update_policy_rule(rule_id: str, request: PolicyRulePatchRequest) -> PolicyRuleItem:
    current_rows = get_supabase_client().table("policy_rules").select("*").eq("id", rule_id).limit(1).execute().data or []
    if not current_rows:
        raise ValueError(f"Policy rule {rule_id} was not found.")

    current = current_rows[0]
    incoming_rule_json = request.rule_json if request.rule_json is not None else execution_rule_json_from_row(current)
    canonical_rule_json, validation_errors = canonicalize_rule_json(
        incoming_rule_json,
        str(current.get("rule_code") or "DRAFT_RULE"),
        str(request.name or current.get("title") or current.get("name") or "Draft rule"),
        request.severity or current.get("severity") or "medium",
    )
    next_status = request.status or policy_rule_status_from_row(current)
    next_enabled = request.enabled if request.enabled is not None else bool(current.get("enabled", current.get("active")))
    activation_errors = activation_guardrail_errors(canonical_rule_json)
    save_errors = validation_errors + (activation_errors if next_status == "active" and next_enabled else [])
    payload: dict[str, Any] = {}

    if request.name is not None:
        payload["title"] = request.name.strip()
    if request.description is not None:
        payload["description"] = request.description.strip()
    if request.severity is not None:
        payload["severity"] = request.severity
    if request.enabled is not None or request.status is not None or request.rule_json is not None:
        payload["active"] = next_status == "active" and next_enabled and not save_errors
        payload["enabled"] = payload["active"]
        payload["status"] = next_status if not save_errors else "draft"
        payload["validation_errors"] = save_errors
        payload["needs_human_review"] = False
    if request.rule_json is not None:
        payload["rule_kind"] = "json_config"
        payload["condition"] = canonical_rule_json.get("condition") or {}
        payload["outcome"] = canonical_rule_json.get("outcome") or {}
        payload["scope"] = canonical_rule_json.get("scope") or {}
        payload["rule_json"] = canonical_rule_json
        payload["conditions_json"] = canonical_rule_json.get("condition") or {}
        payload["outcome_json"] = canonical_rule_json.get("outcome") or {}
        payload["scope_json"] = canonical_rule_json.get("scope") or {}
        payload["applies_to_json"] = canonical_rule_json.get("applies_to") or {}
        payload["thresholds_json"] = canonical_rule_json.get("thresholds") or {}
        payload["context_requirements_json"] = canonical_rule_json.get("context_requirements") or []
        payload["requires_json"] = canonical_rule_json.get("requires") or {}
    if request.source_text is not None:
        payload["source_text"] = request.source_text
    if next_status == "draft":
        payload["synthetic"] = False
    elif next_status == "disabled":
        payload["synthetic"] = True

    updated_rows = execute_policy_rules_write_with_schema_fallback(
        lambda sanitized_payload: (
            get_supabase_client().table("policy_rules").update(sanitized_payload).eq("id", rule_id).execute().data or []
        ),
        payload,
    )
    row = updated_rows[0] if updated_rows else {**current, **payload}
    return policy_rule_item_from_row(row, canonical_rule_json, save_errors, "manual", request.source_text)


def test_policy_rule(rule_id: str, request: PolicyRuleTestRequest | None = None) -> PolicyRuleTestResponse:
    rows = get_supabase_client().table("policy_rules").select("*").eq("id", rule_id).limit(1).execute().data or []
    if not rows:
        raise ValueError(f"Policy rule {rule_id} was not found.")

    test_request = request or PolicyRuleTestRequest(rule_json=execution_rule_json_from_row(rows[0]))
    if not test_request.rule_json:
        test_request = PolicyRuleTestRequest(rule_json=execution_rule_json_from_row(rows[0]))
    return test_draft_policy_rule(test_request)


def test_draft_policy_rule(request: PolicyRuleTestRequest) -> PolicyRuleTestResponse:
    canonical_rule_json, validation_errors = canonicalize_rule_json(
        request.rule_json,
        "DRAFT_RULE",
        "Draft policy rule",
        "medium",
    )
    warnings: list[str] = []
    sample_matches: list[dict[str, Any]] = []
    estimated_impact = {"by_department": {}, "by_employee": {}, "by_category": {}}
    if not validation_errors:
        warnings.extend(activation_guardrail_errors(canonical_rule_json))
    if not validation_errors:
        sample_matches, estimated_impact = sample_configurable_rule_matches(canonical_rule_json, request.sample_limit)
    return PolicyRuleTestResponse(
        valid=not validation_errors,
        matched_count=len(sample_matches),
        sample_matches=sample_matches,
        warnings=warnings,
        validation_errors=validation_errors,
        estimated_impact=estimated_impact,
    )


def extract_policy_rules(
    request: PolicyRuleExtractionRequest,
    ai_client: JsonCompletionClient | None = None,
    policy_document_id: str | None = None,
    policy_extraction_run_id: str | None = None,
) -> PolicyRuleExtractionResponse:
    prepared_request = request.model_copy(
        update={"available_fields": request.available_fields or available_policy_fields()}
    )
    ai_payload = extract_policy_rules_json(prepared_request, client=ai_client)
    draft_rules: list[ExtractedDraftRule] = []
    unsupported = list_of_strings(ai_payload.get("unsupported_or_missing_fields"))
    source_hash = hashlib.sha1(prepared_request.policy_text.encode("utf-8")).hexdigest()[:8]

    for index, raw_rule in enumerate(list_of_dicts(ai_payload.get("draft_rules")), start=1):
        normalized_rule, errors = normalize_extracted_rule(
            raw_rule,
            prepared_request,
            source_hash,
            index,
            policy_document_id=policy_document_id,
            policy_extraction_run_id=policy_extraction_run_id,
        )
        if errors:
            code = str(raw_rule.get("rule_code") or normalized_rule.rule_code or f"rule_{index}")
            unsupported.extend(f"{code}: {error}" for error in errors)
        draft_rules.append(normalized_rule)

    saved_rules = save_extracted_draft_rules(draft_rules) if draft_rules else []
    if any(rule.status == "active" for rule in saved_rules):
        try:
            run_policy_scan_and_refresh(
                PolicyScanRequest(
                    batch_size=500,
                    reset_existing=True,
                    reset_synthetic_evidence=True,
                )
            )
        except Exception as error:
            unsupported.append(
                "Downstream workflow refresh did not complete automatically after activation: "
                f"{error}"
            )
    return PolicyRuleExtractionResponse(
        policy_document_id=policy_document_id,
        draft_rules=saved_rules,
        ambiguities=list_of_strings(ai_payload.get("ambiguities")),
        unsupported_or_missing_fields=unsupported,
        suggested_feature_engineering=list_of_strings(ai_payload.get("suggested_feature_engineering")),
        summary=str(ai_payload.get("summary") or ""),
    )


def evaluate_policy_with_configurable_rules(
    transaction: dict[str, Any],
    receipt: dict[str, Any] | None,
    preapproval: dict[str, Any] | None,
    configurable_rules: list[ConfigurablePolicyRule] | None = None,
) -> PolicyCheckResult:
    return evaluate_policy(
        transaction,
        receipt,
        preapproval,
        rules=configurable_rules or [],
    )


def load_active_configurable_rules() -> list[ConfigurablePolicyRule]:
    rows = (
        get_supabase_client()
        .table("policy_rules")
        .select("*")
        .eq("status", "active")
        .eq("enabled", True)
        .eq("active", True)
        .execute()
        .data
        or []
    )
    rules: list[ConfigurablePolicyRule] = []
    for row in rows:
        rule = configurable_rule_from_row(row)
        if rule:
            rules.append(rule)
    return rules


def configurable_rule_from_row(row: dict[str, Any]) -> ConfigurablePolicyRule | None:
    if row.get("rule_kind") not in {None, "json_config"}:
        return None

    severity = row.get("severity") or "medium"
    if severity not in SEVERITY_RANK:
        severity = "medium"
    canonical_rule_json, errors = canonicalize_rule_json(
        execution_rule_json_from_row(row),
        str(row.get("rule_code") or "CONFIGURABLE_RULE"),
        str(row.get("title") or row.get("name") or row.get("rule_code") or "Configurable rule"),
        severity,
    )
    if errors or activation_guardrail_errors(canonical_rule_json) or not canonical_rule_json:
        return None

    return ConfigurablePolicyRule(
        rule_code=str(canonical_rule_json["rule_code"]),
        name=str(canonical_rule_json["name"]),
        enabled=True,
        severity=canonical_rule_json["severity"],
        condition=canonical_rule_json["condition"],
        outcome=canonical_rule_json["outcome"],
        scope=canonical_rule_json["scope"],
        applies_to=canonical_rule_json["applies_to"],
        thresholds=canonical_rule_json["thresholds"],
        context_requirements=canonical_rule_json["context_requirements"],
    )


def compose_repeat_offender_summary(
    violations: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
    employees: list[dict[str, Any]],
    departments: list[dict[str, Any]],
    limit: int = 5,
) -> RepeatOffenderSummary:
    transactions_by_id = {transaction["id"]: transaction for transaction in transactions}
    employees_by_id = {employee["id"]: employee for employee in employees}
    departments_by_id = {department["id"]: department for department in departments}
    employee_counts: dict[str, int] = {}
    department_counts: dict[str, int] = {}

    for violation in violations:
        if violation.get("status") not in {None, "open"}:
            continue
        transaction = transactions_by_id.get(violation.get("transaction_id") or "")
        if not transaction:
            continue
        if transaction.get("employee_id"):
            employee_counts[transaction["employee_id"]] = employee_counts.get(transaction["employee_id"], 0) + 1
        if transaction.get("department_id"):
            department_counts[transaction["department_id"]] = department_counts.get(transaction["department_id"], 0) + 1

    return RepeatOffenderSummary(
        employees=[
            RepeatOffenderItem(
                id=employee_id,
                name=employees_by_id.get(employee_id, {}).get("full_name") or "Synthetic employee",
                open_violations=count,
            )
            for employee_id, count in sorted(employee_counts.items(), key=lambda item: item[1], reverse=True)[:limit]
        ],
        departments=[
            RepeatOffenderItem(
                id=department_id,
                name=departments_by_id.get(department_id, {}).get("name") or "Synthetic department",
                open_violations=count,
            )
            for department_id, count in sorted(department_counts.items(), key=lambda item: item[1], reverse=True)[:limit]
        ],
    )


def compose_repeat_offender_summary_from_review_queue(
    rows: list[dict[str, Any]],
    employees: list[dict[str, Any]],
    departments: list[dict[str, Any]],
    limit: int = 5,
) -> RepeatOffenderSummary:
    employees_by_id = {employee["id"]: employee for employee in employees}
    departments_by_id = {department["id"]: department for department in departments}
    employee_counts: dict[str, int] = {}
    department_counts: dict[str, int] = {}

    for row in rows:
        if row.get("queue_status") not in {None, "open", "in_approval"}:
            continue
        if not row_has_open_policy_flag(row):
            continue
        if row.get("employee_id"):
            employee_id = str(row["employee_id"])
            employee_counts[employee_id] = employee_counts.get(employee_id, 0) + 1
        if row.get("department_id"):
            department_id = str(row["department_id"])
            department_counts[department_id] = department_counts.get(department_id, 0) + 1

    return RepeatOffenderSummary(
        employees=[
            RepeatOffenderItem(
                id=employee_id,
                name=employees_by_id.get(employee_id, {}).get("full_name") or "Synthetic employee",
                open_violations=count,
            )
            for employee_id, count in sorted(employee_counts.items(), key=lambda item: item[1], reverse=True)[:limit]
        ],
        departments=[
            RepeatOffenderItem(
                id=department_id,
                name=departments_by_id.get(department_id, {}).get("name") or "Synthetic department",
                open_violations=count,
            )
            for department_id, count in sorted(department_counts.items(), key=lambda item: item[1], reverse=True)[:limit]
        ],
    )


def row_has_open_policy_flag(row: dict[str, Any]) -> bool:
    policy_flags = row.get("policy_flags")
    return row.get("policy_status") not in POLICY_CLEAR_STATUSES or bool(policy_flags)


def compose_policy_findings(
    checks: list[dict[str, Any]],
    violations: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
    employees: list[dict[str, Any]],
    departments: list[dict[str, Any]],
) -> list[PolicyFindingItem]:
    transactions_by_id = {transaction["id"]: transaction for transaction in transactions}
    employees_by_id = {employee["id"]: employee for employee in employees}
    departments_by_id = {department["id"]: department for department in departments}
    violations_by_check_id: dict[str, list[dict[str, Any]]] = {}

    for violation in violations:
        policy_check_id = violation.get("policy_check_id")
        if policy_check_id:
            violations_by_check_id.setdefault(str(policy_check_id), []).append(violation)

    findings: list[PolicyFindingItem] = []
    for check in checks:
        transaction = transactions_by_id.get(check.get("transaction_id"))
        if not transaction:
            continue

        employee = employees_by_id.get(transaction.get("employee_id") or "")
        department = departments_by_id.get(transaction.get("department_id") or "")
        merchant = transaction.get("normalized_merchant_name") or transaction.get("merchant_name")
        category = infer_policy_category(transaction)
        nested_violations = compose_nested_violations(
            violations_by_check_id.get(str(check["id"]), []),
            category,
        )

        findings.append(
            PolicyFindingItem(
                transaction_id=transaction["id"],
                employee=employee.get("full_name") if employee else None,
                department=department.get("name") if department else None,
                date=transaction.get("transaction_date"),
                merchant=merchant,
                amount_cad=float(transaction.get("amount_cad") or 0),
                category=category,
                overall_status=check["status"],
                max_severity=check["max_severity"],
                severity_score=int(check.get("severity_score") or 0),
                scan_version=check.get("scan_version") or check.get("engine_version"),
                violations=nested_violations,
                missing_information=check.get("missing_information") or [],
                recommended_next_action=check["recommended_next_action"],
            )
        )

    return findings


def policy_rule_item_from_row(
    row: dict[str, Any],
    rule_json: dict[str, Any] | None = None,
    validation_errors: list[str] | None = None,
    source_type: str | None = None,
    source_text: str | None = None,
) -> PolicyRuleItem:
    status = policy_rule_status_from_row(row)
    return PolicyRuleItem(
        id=str(row.get("id") or ""),
        rule_code=str(row.get("rule_code") or ""),
        name=str(row.get("title") or row.get("name") or ""),
        description=str(row.get("description") or ""),
        severity=row.get("severity") or "medium",
        enabled=bool(row.get("enabled", row.get("active"))),
        status=status,
        deterministic=bool(row.get("deterministic", True)),
        source_type=source_type or str(row.get("source_type") or ("seeded" if row.get("synthetic", True) else "manual")),
        source_text=source_text if source_text is not None else row.get("source_text"),
        rule_json=rule_json or policy_rule_json_from_row(row),
        policy_document_id=str(row.get("policy_document_id")) if row.get("policy_document_id") else None,
        policy_extraction_run_id=str(row.get("policy_extraction_run_id")) if row.get("policy_extraction_run_id") else None,
        extraction_confidence=float(row.get("extraction_confidence")) if row.get("extraction_confidence") is not None else None,
        needs_human_review=bool(row.get("needs_human_review", False)),
        validation_errors=validation_errors or list_of_strings(row.get("validation_errors")),
        updated_at=row.get("updated_at"),
    )


def policy_rule_status_from_row(row: dict[str, Any]) -> PolicyRuleStatus:
    status = row.get("status")
    if status in {"active", "draft", "disabled"}:
        return status
    if row.get("active"):
        return "active"
    if row.get("synthetic") is False:
        return "draft"
    return "disabled"


def validate_rule_json(rule_json: dict[str, Any]) -> list[str]:
    return canonicalize_rule_json(rule_json, "DRAFT_RULE", "Draft policy rule", "medium")[1]


def activation_guardrail_errors(rule_json: dict[str, Any]) -> list[str]:
    if not rule_json:
        return []

    fields = collect_condition_fields(rule_json.get("condition") or {})
    if not fields:
        return []

    errors: list[str] = []
    applies_to = normalize_object(rule_json.get("applies_to") or {})
    has_scoped_applies_to = any(normalize_string_list(value) for value in applies_to.values())
    has_category_or_merchant_scope = bool(fields & CATEGORY_OR_MERCHANT_FIELDS) or has_scoped_applies_to
    has_evidence_fact = bool(fields & EVIDENCE_FIELDS)
    combined_text = policy_rule_search_text(rule_json)

    if fields <= BROAD_ACTIVITY_FIELDS and not has_scoped_applies_to:
        errors.append(
            "Activation blocked: this rule only checks broad card activity fields and can match nearly every transaction."
        )

    if is_amount_only_preauthorization_rule(fields, combined_text):
        errors.append(
            "Activation blocked: preauthorization rules must check approval evidence status, not only amount_cad."
        )

    if "receipt" in combined_text and not has_category_or_merchant_scope and not has_evidence_fact:
        errors.append(
            "Activation blocked: global receipt rules need receipt evidence fields or category/merchant scope to avoid flooding compliance."
        )

    if contains_human_judgment_term(combined_text) and not has_category_or_merchant_scope and not has_evidence_fact:
        errors.append(
            "Activation blocked: human-judgment policy language needs deterministic evidence or category/merchant scope before enforcement."
        )

    return sorted(set(errors))


def is_amount_only_preauthorization_rule(fields: set[str], combined_text: str) -> bool:
    mentions_approval = any(token in combined_text for token in ["approval", "preapproval", "pre-approval", "preauthorization", "pre-author"])
    has_approval_evidence = bool(fields & {"missing_preapproval", "preapproval_status", "requires_preapproval", "has_pending_preapproval"})
    return mentions_approval and fields == {"amount_cad"} and not has_approval_evidence


def contains_human_judgment_term(combined_text: str) -> bool:
    return any(term in combined_text for term in HUMAN_JUDGMENT_TERMS)


def policy_rule_search_text(rule_json: dict[str, Any]) -> str:
    return json.dumps(
        {
            "name": rule_json.get("name"),
            "outcome": rule_json.get("outcome"),
            "requires": rule_json.get("requires"),
            "context_requirements": rule_json.get("context_requirements"),
        },
        sort_keys=True,
        default=str,
    ).lower()


def canonicalize_rule_json(
    rule_json: dict[str, Any],
    rule_code: str,
    name: str,
    severity: Severity,
) -> tuple[dict[str, Any], list[str]]:
    if not rule_json:
        return {}, []
    if not isinstance(rule_json, dict):
        return {}, ["Rule JSON must be an object."]

    condition = normalize_condition_tree(rule_json.get("condition") or rule_json.get("conditions") or {})
    outcome = normalize_rule_outcome(rule_json.get("outcome") or {}, rule_code, severity)
    scope = rule_json.get("scope") or rule_json.get("scope_json") or {}
    applies_to = normalize_object(rule_json.get("applies_to") or rule_json.get("applies_to_json") or {})
    thresholds = normalize_thresholds(
        rule_json.get("thresholds")
        or rule_json.get("thresholds_json")
        or rule_json.get("threshold")
        or {}
    )
    context_requirements = normalize_string_list(
        rule_json.get("context_requirements") or rule_json.get("context_requirements_json") or []
    )
    requires = normalize_requires(rule_json)
    canonical = {
        "rule_code": rule_code.strip().upper(),
        "name": name.strip() or rule_code.strip().upper(),
        "enabled": True,
        "severity": severity,
        "condition": condition,
        "outcome": outcome,
        "scope": normalize_rule_scope(scope),
        "applies_to": applies_to,
        "thresholds": thresholds,
        "context_requirements": context_requirements,
        "requires": requires,
    }

    try:
        validate_configurable_rule(
            ConfigurablePolicyRule(
                rule_code=canonical["rule_code"],
                name=canonical["name"],
                enabled=True,
                severity=severity,
                condition=canonical["condition"],
                outcome=canonical["outcome"],
                scope=canonical["scope"],
                applies_to=canonical["applies_to"],
                thresholds=canonical["thresholds"],
                context_requirements=canonical["context_requirements"],
            )
        )
    except (KeyError, TypeError, ValueError, RuleValidationError) as error:
        message = str(error)
        if message.startswith("Unsupported context field:"):
            field = message.split(":", 1)[1].strip()
            message = f"field '{field}' is not allowed."
        return canonical, [message]

    return canonical, []


def normalize_condition_tree(node: Any) -> dict[str, Any]:
    if not isinstance(node, dict):
        return {}

    if "all" in node:
        return {"all": [normalize_condition_tree(child) for child in node.get("all") or []]}
    if "any" in node:
        return {"any": [normalize_condition_tree(child) for child in node.get("any") or []]}
    if "not" in node:
        return {"not": normalize_condition_tree(node.get("not"))}

    normalized = dict(node)
    operator = normalized.get("operator")
    if operator in LEGACY_OPERATOR_MAP:
        normalized["operator"] = LEGACY_OPERATOR_MAP[operator]
    return normalized


def normalize_rule_outcome(outcome: dict[str, Any], rule_code: str, severity: Severity) -> dict[str, Any]:
    if not isinstance(outcome, dict):
        outcome = {}
    if "violation" in outcome:
        normalized = dict(outcome)
    else:
        message = (
            outcome.get("message_template")
            or outcome.get("message")
            or outcome.get("explanation")
            or "Policy rule matched this transaction."
        )
        required_action = outcome.get("required_action") or "Review the transaction against this policy rule."
        normalized = {
            "violation": {
                "rule_code": rule_code.strip().upper(),
                "severity": outcome.get("severity") or severity,
                "explanation": message,
                "required_action": required_action,
            }
        }
    normalized["status"] = normalize_outcome_status(outcome.get("status")) or normalize_outcome_status(
        normalized.get("status")
    ) or status_from_outcome_fields(normalized, severity)
    violation = normalized.get("violation")
    if isinstance(violation, dict):
        violation.setdefault("rule_code", rule_code.strip().upper())
        violation.setdefault("severity", severity)
    missing_information = list(normalized.get("missing_information") or [])
    for key in ["evidence_type", "context_requirement"]:
        if outcome.get(key):
            missing_information.append(str(outcome[key]))
    normalized["missing_information"] = sorted(set(missing_information))
    return normalized


def status_from_outcome_fields(outcome: dict[str, Any], fallback_severity: Severity) -> PolicyStatus:
    violation = outcome.get("violation")
    severity = fallback_severity
    if isinstance(violation, dict) and violation.get("severity") in SEVERITY_RANK:
        severity = violation["severity"]
    if severity in {"critical", "high"}:
        return "review_required"
    if outcome.get("missing_information"):
        return "context_needed"
    return "review_required"


def normalize_rule_scope(scope: Any) -> dict[str, Any]:
    if not isinstance(scope, dict):
        return {"department_ids": [], "employee_ids": []}
    return {
        "department_ids": scope.get("department_ids") or [],
        "employee_ids": scope.get("employee_ids") or [],
    }


def normalize_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def normalize_thresholds(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        normalized: dict[str, Any] = {}
        for item in value:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("threshold") or "").strip()
            if not name:
                continue
            normalized[name] = normalize_threshold_config(item)
        return normalized
    if isinstance(value, dict):
        if "name" in value and ("value" in value or "default" in value):
            return {str(value["name"]): normalize_threshold_config(value)}
        return {
            str(name): normalize_threshold_config(config)
            for name, config in value.items()
            if str(name).strip()
        }
    return {}


def normalize_threshold_config(value: Any) -> Any:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, dict):
        return value
    normalized = dict(value)
    normalized.pop("name", None)
    for key in ("by_department", "by_employee", "by_role"):
        normalized[key] = normalize_threshold_overrides(normalized.get(key))
    normalized["by_period"] = normalize_threshold_periods(normalized.get("by_period") or normalized.get("periods"))
    return {key: item for key, item in normalized.items() if item not in (None, "", [], {})}


def normalize_threshold_overrides(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items() if str(key).strip() and item not in (None, "")}
    if isinstance(value, list):
        overrides: dict[str, Any] = {}
        for item in value:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or item.get("id") or item.get("name") or "").strip()
            if key and item.get("value") not in (None, ""):
                overrides[key] = item["value"]
        return overrides
    return {}


def normalize_threshold_periods(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    periods = []
    for item in value:
        if not isinstance(item, dict) or item.get("value") in (None, ""):
            continue
        periods.append(
            {
                "start": item.get("start") or item.get("date_start"),
                "end": item.get("end") or item.get("date_end"),
                "value": item.get("value"),
            }
        )
    return periods


def normalize_requires(rule_json: dict[str, Any]) -> dict[str, Any]:
    requires = normalize_object(rule_json.get("requires") or rule_json.get("requires_json") or {})
    required_facts = normalize_string_list(rule_json.get("requires_facts") or [])
    if required_facts:
        requires["facts"] = sorted(set(normalize_string_list(requires.get("facts")) + required_facts))
    evidence_requirements = normalize_string_list(rule_json.get("evidence_requirements") or [])
    if evidence_requirements:
        requires["evidence"] = sorted(set(normalize_string_list(requires.get("evidence")) + evidence_requirements))
    period = normalize_object(rule_json.get("period") or {})
    if period:
        requires["period"] = period
    return requires


def normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def policy_rule_json_from_row(row: dict[str, Any]) -> dict[str, Any]:
    if isinstance(row.get("rule_json"), dict) and row["rule_json"]:
        return row["rule_json"]

    return execution_rule_json_from_row(row)


def execution_rule_json_from_row(row: dict[str, Any]) -> dict[str, Any]:
    condition = row.get("condition") or row.get("conditions_json") or {}
    outcome = row.get("outcome") or row.get("outcome_json") or {}
    scope = row.get("scope") or row.get("scope_json") or {}
    applies_to = row.get("applies_to_json") or {}
    thresholds = row.get("thresholds_json") or normalize_object(row.get("rule_metadata")).get("thresholds") or {}
    context_requirements = row.get("context_requirements_json") or []
    requires = row.get("requires_json") or {}

    if condition or outcome or scope or applies_to or thresholds or context_requirements or requires:
        return {
            "rule_code": row.get("rule_code"),
            "name": row.get("title") or row.get("name"),
            "severity": row.get("severity") or "medium",
            "condition": condition,
            "outcome": outcome,
            "scope": scope,
            "applies_to": applies_to,
            "thresholds": thresholds,
            "context_requirements": context_requirements,
            "requires": requires,
        }
    return {}


def sample_configurable_rule_matches(
    canonical_rule_json: dict[str, Any],
    sample_limit: int,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, int]]]:
    rule = ConfigurablePolicyRule(
        rule_code=str(canonical_rule_json["rule_code"]),
        name=str(canonical_rule_json["name"]),
        enabled=True,
        severity=canonical_rule_json["severity"],
        condition=canonical_rule_json["condition"],
        outcome=canonical_rule_json["outcome"],
        scope=canonical_rule_json["scope"],
        applies_to=canonical_rule_json["applies_to"],
        thresholds=canonical_rule_json["thresholds"],
        context_requirements=canonical_rule_json["context_requirements"],
    )
    rows = (
        get_supabase_client()
        .table("transactions")
        .select("*")
        .order("created_at")
        .limit(max(sample_limit * 20, sample_limit, 1))
        .execute()
        .data
        or []
    )
    sample_matches: list[dict[str, Any]] = []
    estimated_impact: dict[str, dict[str, int]] = {"by_department": {}, "by_employee": {}, "by_category": {}}

    for transaction in enrich_transactions_with_people(rows):
        receipt = infer_synthetic_receipt(transaction)
        preapproval = infer_synthetic_preapproval(transaction) if transaction.get("employee_id") else None
        context = build_policy_context(transaction, receipt, preapproval)
        outcome = evaluate_configurable_rule(rule, context)
        if not outcome.violations and not outcome.missing_information:
            continue

        category = infer_policy_category(transaction)
        increment_count(estimated_impact["by_department"], str(transaction.get("department_id") or "unassigned"))
        increment_count(estimated_impact["by_employee"], str(transaction.get("employee_id") or "unassigned"))
        increment_count(estimated_impact["by_category"], category)
        sample_matches.append(
            {
                "transaction_id": transaction.get("id"),
                "merchant": transaction.get("normalized_merchant_name") or transaction.get("merchant_name"),
                "amount_cad": float(transaction.get("amount_cad") or 0),
                "category": category,
            }
        )
        if len(sample_matches) >= max(sample_limit, 0):
            break

    return sample_matches, estimated_impact


def increment_count(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def validate_condition_tree(node: Any, errors: list[str], path: str) -> None:
    if node in (None, {}):
        return
    if not isinstance(node, dict):
        errors.append(f"{path} must be an object.")
        return

    logic_keys = [key for key in node if key in ALLOWED_RULE_LOGIC_KEYS]
    if logic_keys:
        for key in logic_keys:
            child = node[key]
            if key in {"all", "any"}:
                if not isinstance(child, list):
                    errors.append(f"{path}.{key} must be a list.")
                    continue
                for index, item in enumerate(child):
                    validate_condition_tree(item, errors, f"{path}.{key}[{index}]")
            else:
                validate_condition_tree(child, errors, f"{path}.not")
        return

    operator = node.get("operator")
    field = node.get("field")
    if not field:
        errors.append(f"{path}.field is required.")
    elif field not in ALLOWED_RULE_FIELDS:
        errors.append(f"{path}.field '{field}' is not allowed.")
    if not operator:
        errors.append(f"{path}.operator is required.")
    elif operator not in ALLOWED_RULE_OPERATORS:
        errors.append(f"{path}.operator '{operator}' is not supported yet.")


def preserved_extracted_rule_json(
    raw_rule: dict[str, Any],
    nested_rule_json: dict[str, Any],
) -> dict[str, Any]:
    preserved = deepcopy(nested_rule_json)
    field_sources = {
        "condition": raw_rule.get("condition")
        or raw_rule.get("conditions_json")
        or raw_rule.get("conditions")
        or nested_rule_json.get("condition")
        or nested_rule_json.get("conditions"),
        "outcome": raw_rule.get("outcome_json") or raw_rule.get("outcome") or nested_rule_json.get("outcome"),
        "scope": raw_rule.get("scope_json") or raw_rule.get("scope") or nested_rule_json.get("scope"),
        "applies_to": raw_rule.get("applies_to_json") or raw_rule.get("applies_to") or nested_rule_json.get("applies_to"),
        "thresholds": raw_rule.get("thresholds_json") or raw_rule.get("thresholds") or nested_rule_json.get("thresholds"),
        "context_requirements": raw_rule.get("context_requirements_json")
        or raw_rule.get("context_requirements")
        or nested_rule_json.get("context_requirements"),
        "evidence_requirements": raw_rule.get("evidence_requirements") or nested_rule_json.get("evidence_requirements"),
        "period": raw_rule.get("period")
        or nested_rule_json.get("period")
        or {
            key: value
            for key, value in {
                "start": nested_rule_json.get("period_start"),
                "end": nested_rule_json.get("period_end"),
            }.items()
            if value
        },
        "requires_facts": raw_rule.get("requires_facts") or nested_rule_json.get("requires_facts"),
        "requires": raw_rule.get("requires_json") or raw_rule.get("requires") or nested_rule_json.get("requires"),
    }
    for key, value in field_sources.items():
        if value not in (None, "", [], {}):
            preserved[key] = deepcopy(value)
    return preserved


def normalize_extracted_rule(
    raw_rule: dict[str, Any],
    request: PolicyRuleExtractionRequest,
    source_hash: str,
    index: int,
    policy_document_id: str | None = None,
    policy_extraction_run_id: str | None = None,
) -> tuple[ExtractedDraftRule, list[str]]:
    rule_code = normalized_rule_code(str(raw_rule.get("rule_code") or raw_rule.get("name") or f"AI_RULE_{index}"))
    rule_code = f"{rule_code}_{source_hash}_{index}"
    nested_rule_json = raw_rule.get("rule_json") if isinstance(raw_rule.get("rule_json"), dict) else {}
    source_text = str(raw_rule.get("source_text") or request.policy_text).strip()
    rule_json = preserved_extracted_rule_json(raw_rule, nested_rule_json)

    severity = str(raw_rule.get("severity") or "medium").lower()
    if severity not in SEVERITY_RANK:
        severity = "medium"
    canonical_rule_json, validation_errors = canonicalize_rule_json(
        rule_json,
        rule_code,
        str(raw_rule.get("name") or raw_rule.get("title") or rule_code).strip(),
        severity,  # type: ignore[arg-type]
    )
    if str(raw_rule.get("severity") or "medium").lower() not in SEVERITY_RANK:
        validation_errors.append(f"severity '{raw_rule.get('severity')}' is not supported.")
    validation_errors.extend(validate_available_fields(canonical_rule_json, request.available_fields))

    confidence = raw_rule.get("extraction_confidence")
    if confidence is not None:
        try:
            confidence = max(0.0, min(float(confidence), 1.0))
        except (TypeError, ValueError):
            validation_errors.append("extraction_confidence must be a number between 0 and 1.")
            confidence = None

    needs_human_review = bool(raw_rule.get("needs_human_review")) or bool(validation_errors)

    return (
        ExtractedDraftRule(
            rule_code=rule_code,
            name=str(raw_rule.get("name") or raw_rule.get("title") or rule_code).strip(),
            description=str(raw_rule.get("description") or "").strip(),
            severity=severity,  # type: ignore[arg-type]
            enabled=False,
            status="draft",
            source_type="ai_extracted",
            source_text=source_text or request.policy_text,
            rule_json=rule_json,
            policy_document_id=policy_document_id,
            policy_extraction_run_id=policy_extraction_run_id,
            extraction_confidence=confidence,
            needs_human_review=needs_human_review,
            validation_errors=validation_errors,
        ),
        validation_errors,
    )


def save_extracted_draft_rules(draft_rules: list[ExtractedDraftRule]) -> list[ExtractedDraftRule]:
    if not draft_rules:
        return []

    prepared_rules = [prepared_extracted_rule_for_persistence(rule) for rule in draft_rules]
    payloads = [policy_rule_payload_from_extracted_rule(rule) for rule in prepared_rules]
    rows = execute_policy_rules_write_with_schema_fallback(
        lambda sanitized_payloads: (
            get_supabase_client().table("policy_rules").upsert(sanitized_payloads, on_conflict="rule_code").execute().data or []
        ),
        payloads,
    )
    rows_by_code = {row.get("rule_code"): row for row in rows}
    saved: list[ExtractedDraftRule] = []
    for rule in prepared_rules:
        row = rows_by_code.get(rule.rule_code, {})
        saved.append(rule.model_copy(update={"id": str(row.get("id")) if row.get("id") else rule.id}))
    return saved


def prepared_extracted_rule_for_persistence(rule: ExtractedDraftRule) -> ExtractedDraftRule:
    canonical_rule_json, validation_errors = canonicalize_rule_json(
        rule.rule_json,
        rule.rule_code,
        rule.name,
        rule.severity,
    )
    blocking_errors = sorted(
        {
            *rule.validation_errors,
            *validation_errors,
            *activation_guardrail_errors(canonical_rule_json),
        }
    )
    can_activate = len(blocking_errors) == 0
    return rule.model_copy(
        update={
            "enabled": can_activate,
            "status": "active" if can_activate else "draft",
            "needs_human_review": False,
            "validation_errors": blocking_errors,
        }
    )


def policy_rule_payload_from_extracted_rule(rule: ExtractedDraftRule) -> dict[str, Any]:
    canonical_rule_json, _ = canonicalize_rule_json(
        rule.rule_json,
        rule.rule_code,
        rule.name,
        rule.severity,
    )
    execution_rule_json = canonical_rule_json or {}
    return {
        "rule_code": rule.rule_code,
        "title": rule.name,
        "name": rule.name,
        "description": rule.description,
        "severity": rule.severity,
        "deterministic": True,
        "active": rule.status == "active" and rule.enabled,
        "enabled": rule.enabled,
        "status": rule.status,
        "priority": 100,
        "synthetic": False,
        "editable": True,
        "version": 1,
        "source_type": "ai_extracted",
        "source_text": rule.source_text,
        "policy_document_id": rule.policy_document_id,
        "policy_extraction_run_id": rule.policy_extraction_run_id,
        "rule_json": rule.rule_json,
        "condition": execution_rule_json.get("condition") or {},
        "outcome": execution_rule_json.get("outcome") or {},
        "scope": execution_rule_json.get("scope") or {},
        "rule_kind": "json_config",
        "conditions_json": execution_rule_json.get("condition") or {},
        "outcome_json": execution_rule_json.get("outcome") or {},
        "scope_json": execution_rule_json.get("scope") or {},
        "applies_to_json": execution_rule_json.get("applies_to") or {},
        "thresholds_json": execution_rule_json.get("thresholds") or {},
        "context_requirements_json": execution_rule_json.get("context_requirements") or [],
        "requires_json": execution_rule_json.get("requires") or {},
        "extraction_confidence": rule.extraction_confidence,
        "needs_human_review": False,
        "validation_errors": rule.validation_errors,
    }


def execute_policy_rules_write_with_schema_fallback(
    operation: Callable[[Any], list[dict[str, Any]]],
    payload: dict[str, Any] | list[dict[str, Any]],
) -> list[dict[str, Any]]:
    sanitized_payload = payload
    stripped_columns: set[str] = set()

    while True:
        try:
            return operation(sanitized_payload)
        except Exception as error:
            missing_column = missing_policy_rules_schema_column(error)
            if not missing_column or missing_column in stripped_columns:
                raise
            sanitized_payload = strip_column_from_policy_rule_payload(sanitized_payload, missing_column)
            stripped_columns.add(missing_column)


def missing_policy_rules_schema_column(error: Exception) -> str | None:
    message = str(getattr(error, "message", "") or error)
    match = re.search(r"Could not find the '([^']+)' column of 'policy_rules' in the schema cache", message)
    if not match:
        return None
    return match.group(1)


def strip_column_from_policy_rule_payload(
    payload: dict[str, Any] | list[dict[str, Any]],
    column_name: str,
) -> dict[str, Any] | list[dict[str, Any]]:
    if isinstance(payload, list):
        return [{key: value for key, value in item.items() if key != column_name} for item in payload]
    return {key: value for key, value in payload.items() if key != column_name}


def validate_available_fields(rule_json: dict[str, Any], available_fields: list[str] | None) -> list[str]:
    if not available_fields:
        return []

    allowed_available_fields = set(available_fields) & set(ALLOWED_CONTEXT_FIELDS)
    missing = sorted(collect_condition_fields(rule_json.get("condition", rule_json)) - allowed_available_fields)
    return [f"field '{field}' is not available in this transaction context." for field in missing]


def collect_condition_fields(node: Any) -> set[str]:
    if not isinstance(node, dict):
        return set()
    fields: set[str] = set()
    if isinstance(node.get("field"), str):
        fields.add(node["field"])
    for key in ALLOWED_RULE_LOGIC_KEYS:
        child = node.get(key)
        if isinstance(child, list):
            for item in child:
                fields.update(collect_condition_fields(item))
        elif isinstance(child, dict):
            fields.update(collect_condition_fields(child))
    return fields


def list_of_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def normalized_rule_code(value: str) -> str:
    normalized = re.sub(r"[^A-Z0-9]+", "_", value.upper()).strip("_")
    return normalized[:48] or "AI_RULE"


def available_policy_fields() -> list[str]:
    return sorted(set(ALLOWED_RULE_FIELDS) | set(ALLOWED_CONTEXT_FIELDS))


def policy_document_item_from_row(row: dict[str, Any]) -> PolicyDocumentItem:
    extraction_status = str(row.get("extraction_status") or "pending")
    if extraction_status not in {"pending", "extracted", "failed"}:
        extraction_status = "pending"
    source_type = str(row.get("source_type") or "seed")
    if source_type not in {"seed", "pasted_text", "uploaded_pdf"}:
        source_type = "seed"
    return PolicyDocumentItem(
        id=str(row.get("id") or ""),
        title=str(row.get("title") or ""),
        version=str(row.get("version") or ""),
        source_type=source_type,  # type: ignore[arg-type]
        file_name=str(row.get("file_name")) if row.get("file_name") else None,
        storage_path=str(row.get("storage_path")) if row.get("storage_path") else None,
        raw_text=str(row.get("raw_text")) if row.get("raw_text") else None,
        extracted_text=str(row.get("extracted_text")) if row.get("extracted_text") else None,
        extraction_status=extraction_status,  # type: ignore[arg-type]
        extraction_error=str(row.get("extraction_error")) if row.get("extraction_error") else None,
        active=bool(row.get("active", True)),
        synthetic=bool(row.get("synthetic", False)),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def policy_document_create_response_from_row(
    row: dict[str, Any],
    rag_result: PolicyRagIngestionResult | None = None,
) -> PolicyDocumentCreateResponse:
    document = policy_document_item_from_row(row)
    text = document.extracted_text or document.raw_text or ""
    return PolicyDocumentCreateResponse(
        policy_document_id=document.id,
        document=document,
        text_preview=policy_text_preview(text),
        char_count=len(text),
        embedding_status=rag_result.status if rag_result else None,
        embedding_error=rag_result.error if rag_result else None,
        chunk_count=rag_result.chunk_count if rag_result else 0,
        embedded_chunk_count=rag_result.embedded_count if rag_result else 0,
    )


def ingest_policy_document_for_rag(row: dict[str, Any]) -> PolicyRagIngestionResult:
    try:
        return ingest_policy_document_chunks(row)
    except Exception as error:
        return PolicyRagIngestionResult(
            status="failed",
            error=f"Policy RAG ingestion failed: {error}",
        )


def policy_extraction_run_from_row(row: dict[str, Any]) -> PolicyExtractionRunItem:
    status = str(row.get("status") or "pending")
    if status not in {"pending", "completed", "failed"}:
        status = "pending"
    return PolicyExtractionRunItem(
        id=str(row.get("id") or ""),
        policy_document_id=str(row.get("policy_document_id") or ""),
        model_used=str(row.get("model_used")) if row.get("model_used") else None,
        status=status,  # type: ignore[arg-type]
        summary=str(row.get("summary")) if row.get("summary") else None,
        ambiguities=list_of_strings(row.get("ambiguities")),
        unsupported_or_missing_fields=list_of_strings(row.get("unsupported_or_missing_fields")),
        suggested_feature_engineering=list_of_strings(row.get("suggested_feature_engineering")),
        draft_rule_count=int(row.get("draft_rule_count") or 0),
        error=str(row.get("error")) if row.get("error") else None,
        created_at=row.get("created_at"),
    )


def get_policy_document(policy_document_id: str) -> dict[str, Any] | None:
    rows = (
        get_supabase_client()
        .table("policy_documents")
        .select("*")
        .eq("id", policy_document_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    return rows[0] if rows else None


def create_policy_extraction_run(policy_document_id: str) -> PolicyExtractionRunItem:
    settings = get_settings()
    provider = (settings.ai_rule_extraction_provider or "").strip().lower()
    if not provider:
        provider = "openai" if settings.openai_api_key else "anthropic"
    model = settings.ai_rule_extraction_model
    if not model:
        model = settings.openai_rule_extraction_model if provider == "openai" else settings.anthropic_model
    payload = {
        "policy_document_id": policy_document_id,
        "model_used": f"{provider}:{model}",
        "status": "pending",
    }
    rows = get_supabase_client().table("policy_extraction_runs").insert(payload).execute().data or []
    row = rows[0] if rows else payload
    return policy_extraction_run_from_row(row)


def update_policy_extraction_run(run_id: str, payload: dict[str, Any]) -> PolicyExtractionRunItem:
    rows = (
        get_supabase_client()
        .table("policy_extraction_runs")
        .update(payload)
        .eq("id", run_id)
        .execute()
        .data
        or []
    )
    row = rows[0] if rows else {"id": run_id, **payload}
    return policy_extraction_run_from_row(row)


def clear_policy_document_extraction_error(policy_document_id: str) -> None:
    get_supabase_client().table("policy_documents").update(
        {"extraction_status": "extracted", "extraction_error": None}
    ).eq("id", policy_document_id).execute()


def normalize_policy_document_text(value: str) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def prepared_policy_text_for_extraction(policy_text: str) -> tuple[str, str | None]:
    normalized = normalize_policy_document_text(policy_text)
    if len(normalized) <= POLICY_TEXT_EXTRACTION_LIMIT:
        return normalized, None
    return (
        normalized[:POLICY_TEXT_EXTRACTION_LIMIT],
        f"Only the first {POLICY_TEXT_EXTRACTION_LIMIT} characters were sent for draft extraction. Split very long policies into smaller sections for higher fidelity.",
    )


def generated_policy_document_version(source_hint: str) -> str:
    timestamp = re.sub(r"[^0-9]", "", utc_now_iso())[:14]
    return f"{source_hint}-{timestamp}-{uuid4().hex[:6]}"


def policy_text_preview(text: str, limit: int = POLICY_TEXT_PREVIEW_CHARS) -> str:
    normalized = normalize_policy_document_text(text)
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit].rstrip()}..."


def sanitized_policy_file_name(file_name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", file_name or "policy.pdf").strip("._")
    if not cleaned:
        cleaned = "policy.pdf"
    if not cleaned.lower().endswith(".pdf"):
        cleaned = f"{cleaned}.pdf"
    return cleaned


def policy_document_title_from_file_name(file_name: str) -> str:
    stem = re.sub(r"\.pdf$", "", file_name, flags=re.IGNORECASE)
    title = re.sub(r"[_-]+", " ", stem).strip()
    return title.title() or "Uploaded policy"


@lru_cache(maxsize=1)
def ensure_policy_documents_bucket() -> None:
    storage = get_supabase_client().storage
    try:
        storage.get_bucket(POLICY_DOCUMENTS_BUCKET)
    except Exception:
        storage.create_bucket(
            POLICY_DOCUMENTS_BUCKET,
            options={"public": False, "allowed_mime_types": ["application/pdf"]},
        )


def upload_policy_document_bytes(document_id: str, file_name: str, file_bytes: bytes) -> str:
    ensure_policy_documents_bucket()
    path = f"{document_id}/{file_name}"
    get_supabase_client().storage.from_(POLICY_DOCUMENTS_BUCKET).upload(
        path=path,
        file=file_bytes,
        file_options={"content-type": "application/pdf", "upsert": "false"},
    )
    return path


def extract_text_from_pdf_bytes(file_bytes: bytes) -> str:
    try:
        import fitz
    except ImportError as error:
        raise RuntimeError("PyMuPDF is required for PDF policy uploads. Install backend requirements first.") from error

    document = fitz.open(stream=file_bytes, filetype="pdf")
    try:
        extracted_pages = []
        for page in document:
            page_text = page.get_text("text").strip()
            if page_text:
                extracted_pages.append(page_text)
    finally:
        document.close()

    return normalize_policy_document_text("\n\n".join(extracted_pages))


def compose_nested_violations(violations: list[dict[str, Any]], category: str) -> list[PolicyViolation]:
    del category

    rows_by_rule_code: dict[str, dict[str, Any]] = {}
    for violation in violations:
        rule_code = str(violation.get("rule_code") or "")
        existing = rows_by_rule_code.get(rule_code)
        if not existing or SEVERITY_RANK.get(str(violation.get("severity")), 0) > SEVERITY_RANK.get(
            str(existing.get("severity")),
            0,
        ):
            rows_by_rule_code[rule_code] = violation

    nested = [
        PolicyViolation(
            rule_code=violation["rule_code"],
            severity=violation["severity"],
            explanation=violation["explanation"],
            required_action=violation["required_action"],
        )
        for violation in sorted(
            rows_by_rule_code.values(),
            key=lambda violation: (SEVERITY_RANK.get(violation.get("severity"), 0), violation.get("rule_code") or ""),
            reverse=True,
        )
    ]
    return sorted(nested, key=lambda violation: (SEVERITY_RANK[violation.severity], violation.rule_code), reverse=True)


def fetch_policy_checks(
    severity: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    start = 0
    while True:
        query = (
            get_supabase_client()
            .table("policy_checks")
            .select("*")
            .order("checked_at", desc=True)
            .order("id", desc=True)
        )
        if severity:
            query = query.eq("max_severity", severity)
        if status:
            query = query.eq("status", status)
        else:
            query = query.neq("status", "compliant")

        batch = query.range(start, start + PAGE_SIZE - 1).execute().data or []
        checks.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        start += PAGE_SIZE

    return dedupe_policy_checks(checks)


def enrich_transactions_with_people(transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not transactions:
        return []

    employees = fetch_by_ids("employees", unique_ids(transaction.get("employee_id") for transaction in transactions))
    departments = fetch_by_ids("departments", unique_ids(transaction.get("department_id") for transaction in transactions))
    employees_by_id = {employee["id"]: employee for employee in employees}
    departments_by_id = {department["id"]: department for department in departments}

    enriched: list[dict[str, Any]] = []
    for transaction in transactions:
        employee = employees_by_id.get(transaction.get("employee_id") or "")
        department = departments_by_id.get(transaction.get("department_id") or "")
        enriched.append(
            {
                **transaction,
                "employee_name": transaction.get("employee_name") or (employee or {}).get("full_name"),
                "employee_role": transaction.get("employee_role") or (employee or {}).get("role"),
                "department_name": transaction.get("department_name") or (department or {}).get("name"),
            }
        )

    return enriched


def fetch_transaction(transaction_id: str) -> dict[str, Any] | None:
    rows = (
        get_supabase_client()
        .table("transactions")
        .select("*, raw_transactions(source_fingerprint)")
        .eq("id", transaction_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    return rows[0] if rows else None


def iter_transaction_batches(request: PolicyScanRequest, batch_size: int):
    start = 0
    remaining = request.limit

    while True:
        requested_size = batch_size if remaining is None else min(batch_size, remaining)
        if requested_size <= 0:
            break

        batch = fetch_transactions_page(request, start, requested_size)
        if not batch:
            break

        yield batch

        if remaining is not None:
            remaining -= len(batch)
            if remaining <= 0:
                break
        if len(batch) < requested_size:
            break

        start += len(batch)


def fetch_transactions_page(request: PolicyScanRequest, start: int, batch_size: int) -> list[dict[str, Any]]:
    query = get_supabase_client().table("transactions").select("*, raw_transactions(source_fingerprint)").order("created_at")
    if request.department_id:
        query = query.eq("department_id", request.department_id)
    if request.employee_id:
        query = query.eq("employee_id", request.employee_id)
    if request.date_start:
        query = query.gte("transaction_date", request.date_start)
    if request.date_end:
        query = query.lte("transaction_date", request.date_end)

    return query.range(start, start + batch_size - 1).execute().data or []


def fetch_transactions(request: PolicyScanRequest) -> list[dict[str, Any]]:
    client = get_supabase_client()
    transactions: list[dict[str, Any]] = []
    start = 0

    while True:
        query = client.table("transactions").select("*, raw_transactions(source_fingerprint)").order("created_at")
        if request.department_id:
            query = query.eq("department_id", request.department_id)
        if request.employee_id:
            query = query.eq("employee_id", request.employee_id)
        if request.date_start:
            query = query.gte("transaction_date", request.date_start)
        if request.date_end:
            query = query.lte("transaction_date", request.date_end)

        batch = query.range(start, start + PAGE_SIZE - 1).execute().data or []
        transactions.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        start += PAGE_SIZE

    return transactions


def resolve_receipts(
    transactions: list[dict[str, Any]],
    reset_synthetic_evidence: bool,
    dry_run: bool,
) -> dict[str, dict[str, Any]]:
    if not dry_run:
        return ensure_receipts(transactions, reset_synthetic_evidence)

    existing = latest_by_transaction_id(fetch_by_transaction_ids("receipts", [transaction["id"] for transaction in transactions]))
    for transaction in transactions:
        existing.setdefault(transaction["id"], infer_synthetic_receipt(transaction))
    return existing


def resolve_preapprovals(
    transactions: list[dict[str, Any]],
    reset_synthetic_evidence: bool,
    dry_run: bool,
    active_configurable_rules: list[ConfigurablePolicyRule] | None = None,
) -> dict[str, dict[str, Any]]:
    if not dry_run:
        return ensure_preapprovals(transactions, reset_synthetic_evidence, active_configurable_rules)

    existing = latest_by_transaction_id(fetch_by_transaction_ids("preapprovals", [transaction["id"] for transaction in transactions]))
    for transaction in transactions:
        if transaction.get("employee_id"):
            existing.setdefault(
                transaction["id"],
                infer_synthetic_preapproval(
                    transaction,
                    thresholds=policy_thresholds_from_rules(active_configurable_rules or [], transaction),
                ),
            )
    return existing


def get_or_create_receipt(transaction: dict[str, Any], reset_synthetic_evidence: bool) -> dict[str, Any]:
    client = get_supabase_client()
    existing_rows = (
        client.table("receipts")
        .select("*")
        .eq("transaction_id", transaction["id"])
        .order("created_at", desc=True)
        .limit(1)
        .execute()
        .data
        or []
    )
    synthetic_receipt = infer_synthetic_receipt(transaction)

    if existing_rows:
        existing = existing_rows[0]
        if reset_synthetic_evidence and existing.get("synthetic"):
            updated = client.table("receipts").update(synthetic_receipt).eq("id", existing["id"]).execute().data or []
            return updated[0] if updated else {**existing, **synthetic_receipt}
        return existing

    inserted = client.table("receipts").insert(synthetic_receipt).execute().data or []
    return inserted[0] if inserted else synthetic_receipt


def ensure_receipts(transactions: list[dict[str, Any]], reset_synthetic_evidence: bool) -> dict[str, dict[str, Any]]:
    transaction_ids = [transaction["id"] for transaction in transactions]
    existing = latest_by_transaction_id(fetch_by_transaction_ids("receipts", transaction_ids))
    updated_payloads: list[dict[str, Any]] = []
    missing_payloads: list[dict[str, Any]] = []

    for transaction in transactions:
        current = existing.get(transaction["id"])
        synthetic_receipt = infer_synthetic_receipt(transaction)
        if current:
            if reset_synthetic_evidence and current.get("synthetic"):
                updated_payload = {**synthetic_receipt, "id": current["id"]}
                updated_payloads.append(updated_payload)
                existing[transaction["id"]] = {**current, **updated_payload}
            continue
        missing_payloads.append(synthetic_receipt)

    for chunk in chunked(updated_payloads, PAGE_SIZE):
        updated = get_supabase_client().table("receipts").upsert(chunk).execute().data or []
        for receipt in updated:
            existing[receipt["transaction_id"]] = receipt

    for chunk in chunked(missing_payloads, PAGE_SIZE):
        inserted = get_supabase_client().table("receipts").insert(chunk).execute().data or []
        for receipt in inserted:
            existing[receipt["transaction_id"]] = receipt

    return existing


def get_or_create_preapproval(
    transaction: dict[str, Any],
    reset_synthetic_evidence: bool,
    thresholds: Any = None,
) -> dict[str, Any] | None:
    if not transaction.get("employee_id"):
        return None

    client = get_supabase_client()
    existing_rows = (
        client.table("preapprovals")
        .select("*")
        .eq("transaction_id", transaction["id"])
        .order("created_at", desc=True)
        .limit(1)
        .execute()
        .data
        or []
    )
    synthetic_preapproval = infer_synthetic_preapproval(transaction, thresholds=thresholds)

    if existing_rows:
        existing = existing_rows[0]
        if reset_synthetic_evidence and existing.get("synthetic"):
            updated = (
                client.table("preapprovals").update(synthetic_preapproval).eq("id", existing["id"]).execute().data
                or []
            )
            return updated[0] if updated else {**existing, **synthetic_preapproval}
        return existing

    inserted = client.table("preapprovals").insert(synthetic_preapproval).execute().data or []
    return inserted[0] if inserted else synthetic_preapproval


def ensure_preapprovals(
    transactions: list[dict[str, Any]],
    reset_synthetic_evidence: bool,
    active_configurable_rules: list[ConfigurablePolicyRule] | None = None,
) -> dict[str, dict[str, Any]]:
    transaction_ids = [transaction["id"] for transaction in transactions]
    existing = latest_by_transaction_id(fetch_by_transaction_ids("preapprovals", transaction_ids))
    updated_payloads: list[dict[str, Any]] = []
    missing_payloads: list[dict[str, Any]] = []

    for transaction in transactions:
        if not transaction.get("employee_id"):
            continue
        current = existing.get(transaction["id"])
        synthetic_preapproval = infer_synthetic_preapproval(
            transaction,
            thresholds=policy_thresholds_from_rules(active_configurable_rules or [], transaction),
        )
        if current:
            if reset_synthetic_evidence and current.get("synthetic"):
                updated_payload = {**synthetic_preapproval, "id": current["id"]}
                updated_payloads.append(updated_payload)
                existing[transaction["id"]] = {**current, **updated_payload}
            continue
        missing_payloads.append(synthetic_preapproval)

    for chunk in chunked(updated_payloads, PAGE_SIZE):
        updated = get_supabase_client().table("preapprovals").upsert(chunk).execute().data or []
        for preapproval in updated:
            existing[preapproval["transaction_id"]] = preapproval

    for chunk in chunked(missing_payloads, PAGE_SIZE):
        inserted = get_supabase_client().table("preapprovals").insert(chunk).execute().data or []
        for preapproval in inserted:
            existing[preapproval["transaction_id"]] = preapproval

    return existing


def persist_policy_result(result: PolicyCheckResult) -> str:
    client = get_supabase_client()
    existing_rows = (
        client.table("policy_checks")
        .select("id")
        .eq("transaction_id", result.transaction_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
        .data
        or []
    )
    check_payload = {
        "transaction_id": result.transaction_id,
        "status": result.status,
        "max_severity": result.max_severity,
        "severity_score": result.severity_score,
        "scan_version": result.scan_version or ENGINE_VERSION,
        "missing_information": result.missing_information,
        "recommended_next_action": result.recommended_next_action,
        "checked_at": utc_now_iso(),
        "engine_version": ENGINE_VERSION,
    }

    if existing_rows:
        check_id = existing_rows[0]["id"]
        client.table("policy_checks").update(check_payload).eq("id", check_id).execute()
    else:
        inserted = client.table("policy_checks").insert(check_payload).execute().data or []
        check_id = inserted[0]["id"]

    client.table("violations").delete().eq("transaction_id", result.transaction_id).execute()
    if result.violations:
        rule_ids = policy_rule_ids_by_code()
        client.table("violations").insert(
            [
                {
                    "policy_check_id": check_id,
                    "transaction_id": result.transaction_id,
                    "policy_rule_id": rule_ids.get(violation.rule_code),
                    "rule_code": violation.rule_code,
                    "severity": violation.severity,
                    "explanation": violation.explanation,
                    "required_action": violation.required_action,
                    "status": "open",
                }
                for violation in result.violations
            ]
        ).execute()

    return check_id


def persist_policy_results(
    results: list[PolicyCheckResult],
    transaction_ids: list[str],
    reset_existing: bool = False,
) -> None:
    if not results:
        return

    client = get_supabase_client()
    if reset_existing:
        for chunk in chunked(transaction_ids, PAGE_SIZE):
            client.table("policy_checks").delete().in_("transaction_id", chunk).execute()

    check_payloads = [policy_check_payload(result) for result in results]

    for chunk in chunked(check_payloads, PAGE_SIZE):
        client.table("policy_checks").upsert(chunk, on_conflict="transaction_id").execute()

    checks_by_transaction_id = latest_by_transaction_id(fetch_by_transaction_ids("policy_checks", transaction_ids))

    for chunk in chunked(transaction_ids, PAGE_SIZE):
        client.table("violations").delete().in_("transaction_id", chunk).execute()

    rule_ids = policy_rule_ids_by_code()
    violation_payloads: list[dict[str, Any]] = []
    for result in results:
        policy_check = checks_by_transaction_id.get(result.transaction_id)
        if not policy_check:
            continue
        for violation in result.violations:
            violation_payloads.append(
                {
                    "policy_check_id": policy_check["id"],
                    "transaction_id": result.transaction_id,
                    "policy_rule_id": rule_ids.get(violation.rule_code),
                    "rule_code": violation.rule_code,
                    "severity": violation.severity,
                    "explanation": violation.explanation,
                    "required_action": violation.required_action,
                    "status": "open",
                }
            )

    for chunk in chunked(violation_payloads, PAGE_SIZE):
        client.table("violations").insert(chunk).execute()


def policy_check_payload(result: PolicyCheckResult) -> dict[str, Any]:
    return {
        "transaction_id": result.transaction_id,
        "status": result.status,
        "max_severity": result.max_severity,
        "severity_score": result.severity_score,
        "scan_version": result.scan_version or ENGINE_VERSION,
        "missing_information": result.missing_information,
        "recommended_next_action": result.recommended_next_action,
        "checked_at": utc_now_iso(),
        "engine_version": ENGINE_VERSION,
    }


def fetch_rows_for_reset(table_name: str, select_clause: str, warnings: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0

    while True:
        try:
            batch = (
                get_supabase_client()
                .table(table_name)
                .select(select_clause)
                .range(start, start + PAGE_SIZE - 1)
                .execute()
                .data
                or []
            )
        except Exception as error:
            if start == 0 and "storage_path" in select_clause and is_missing_schema_error(error):
                warnings.append(f"Skipped {table_name}.storage_path lookup because that column is not available in this database.")
                return fetch_rows_for_reset(table_name, "id", warnings)
            warnings.append(f"Could not inspect {table_name} before reset: {error}")
            return rows

        if not batch:
            break

        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            break

        start += PAGE_SIZE

    return rows


def delete_rows_for_reset(table_name: str, warnings: list[str]) -> int:
    rows = fetch_rows_for_reset(table_name, "id", warnings)
    row_ids = unique_ids(row.get("id") for row in rows)
    if not row_ids:
        return 0

    deleted = 0
    for chunk in chunked(row_ids, PAGE_SIZE):
        try:
            get_supabase_client().table(table_name).delete().in_("id", chunk).execute()
            deleted += len(chunk)
        except Exception as error:
            warnings.append(f"Could not delete rows from {table_name}: {error}")
            break
    return deleted


def delete_rows_by_boolean_flag(table_name: str, column_name: str, value: bool, warnings: list[str]) -> int:
    rows: list[dict[str, Any]] = []
    start = 0

    while True:
        try:
            batch = (
                get_supabase_client()
                .table(table_name)
                .select("id")
                .eq(column_name, value)
                .range(start, start + PAGE_SIZE - 1)
                .execute()
                .data
                or []
            )
        except Exception as error:
            if is_missing_schema_error(error):
                warnings.append(f"Skipped {table_name} cleanup because {column_name} is not available in this database.")
                return 0
            warnings.append(f"Could not inspect {table_name} before reset: {error}")
            return 0

        if not batch:
            break

        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            break

        start += PAGE_SIZE

    row_ids = unique_ids(row.get("id") for row in rows)
    if not row_ids:
        return 0

    deleted = 0
    for chunk in chunked(row_ids, PAGE_SIZE):
        try:
            get_supabase_client().table(table_name).delete().in_("id", chunk).execute()
            deleted += len(chunk)
        except Exception as error:
            warnings.append(f"Could not delete rows from {table_name}: {error}")
            break
    return deleted


def remove_policy_storage_paths(storage_paths: list[str], warnings: list[str]) -> int:
    if not storage_paths:
        return 0

    removed = 0
    for chunk in chunked(storage_paths, 100):
        try:
            get_supabase_client().storage.from_(POLICY_DOCUMENTS_BUCKET).remove(chunk)
            removed += len(chunk)
        except Exception as error:
            warnings.append(f"Could not remove stored policy documents from {POLICY_DOCUMENTS_BUCKET}: {error}")
            break
    return removed


def is_missing_schema_error(error: Exception) -> bool:
    message = str(error).lower()
    return any(
        snippet in message
        for snippet in (
            "column",
            "relation",
            "schema cache",
            "does not exist",
            "could not find",
        )
    )


@lru_cache
def policy_rule_ids_by_code() -> dict[str, str]:
    rows = get_supabase_client().table("policy_rules").select("id,rule_code").execute().data or []
    return {row["rule_code"]: row["id"] for row in rows}


def fetch_by_transaction_ids(table_name: str, transaction_ids: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for chunk in chunked(transaction_ids, PAGE_SIZE):
        rows.extend(get_supabase_client().table(table_name).select("*").in_("transaction_id", chunk).execute().data or [])
    return rows


def fetch_open_violations() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        batch = (
            get_supabase_client()
            .table("violations")
            .select("id,transaction_id,status")
            .eq("status", "open")
            .range(start, start + PAGE_SIZE - 1)
            .execute()
            .data
            or []
        )
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        start += PAGE_SIZE

    return rows


def fetch_open_review_queue_policy_flags() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        try:
            batch = (
                get_supabase_client()
                .table("review_queue_items")
                .select("id,employee_id,department_id,queue_status,policy_status,policy_flags")
                .in_("queue_status", ["open", "in_approval"])
                .range(start, start + PAGE_SIZE - 1)
                .execute()
                .data
                or []
            )
        except Exception:
            return []

        rows.extend(row for row in batch if row_has_open_policy_flag(row))
        if len(batch) < PAGE_SIZE:
            break
        start += PAGE_SIZE

    return rows


def latest_by_transaction_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in sorted(rows, key=lambda item: str(item.get("created_at") or "")):
        transaction_id = row.get("transaction_id")
        if transaction_id:
            latest[transaction_id] = row
    return latest


def fetch_by_ids(table_name: str, ids: list[str]) -> list[dict[str, Any]]:
    if not ids:
        return []
    rows: list[dict[str, Any]] = []
    for chunk in chunked(ids, PAGE_SIZE):
        rows.extend(get_supabase_client().table(table_name).select("*").in_("id", chunk).execute().data or [])
    return rows


def chunked[T](items: list[T], size: int) -> list[list[T]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def unique_ids(values: Any) -> list[str]:
    return sorted({str(value) for value in values if value})


def count_table(table_name: str) -> int:
    response = get_supabase_client().table(table_name).select("*", count="exact", head=True).execute()
    return int(getattr(response, "count", 0) or 0)


def count_evidence_required_transactions() -> int:
    transaction_ids: set[str] = set()
    start = 0
    while True:
        batch = (
            get_supabase_client()
            .table("violations")
            .select("transaction_id")
            .in_("rule_code", ["RECEIPT_REQUIRED", "RECEIPT_EVIDENCE_REQUIRED"])
            .range(start, start + PAGE_SIZE - 1)
            .execute()
            .data
            or []
        )
        transaction_ids.update(str(row["transaction_id"]) for row in batch if row.get("transaction_id"))
        if len(batch) < PAGE_SIZE:
            break
        start += PAGE_SIZE

    return len(transaction_ids)


def dedupe_policy_checks(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen_transaction_ids: set[str] = set()

    for check in checks:
        transaction_id = str(check.get("transaction_id") or "")
        if not transaction_id or transaction_id in seen_transaction_ids:
            continue
        seen_transaction_ids.add(transaction_id)
        deduped.append(check)

    return deduped


def apply_result_to_summary(summary: PolicyScanSummary, result: PolicyCheckResult) -> None:
    summary.total_scanned += 1
    setattr(summary, result.status, getattr(summary, result.status) + 1)
    if result.status == "approval_evidence_needed":
        summary.approval_evidence_required += 1
    if result.status == "policy_violation":
        summary.policy_violations += 1
    if result.max_severity in {"high", "critical"}:
        summary.high_or_critical += 1
    if any(violation.rule_code in {"RECEIPT_REQUIRED", "RECEIPT_EVIDENCE_REQUIRED"} for violation in result.violations):
        summary.evidence_required += 1
    summary.individual_flags += len(result.violations)
    summary.violations_created += len(result.violations)


def normalized_batch_size(batch_size: int) -> int:
    return max(1, min(int(batch_size or PAGE_SIZE), 1000))
