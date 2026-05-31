from app.schemas.policy import (
    PolicyCheckResult,
    PolicyDocumentCreateResponse,
    PolicyDocumentExtractRequest,
    PolicyDocumentTextRequest,
    PolicyFindingItem,
    PolicyResetResponse,
    PolicyRuleExtractionRequest,
    PolicyRuleExtractionResponse,
    PolicyRuleItem,
    PolicyRulePatchRequest,
    PolicyRuleTestRequest,
    PolicyRuleTestResponse,
    PolicyRuleWriteRequest,
    PolicyScanRequest,
    PolicyScanSummary,
    RepeatOffenderSummary,
    ViolationListItem,
)
from app.services.policy_service import (
    check_transaction_policy,
    clear_policy_data,
    create_policy_document_from_text,
    extract_policy_rules_for_document,
    create_policy_rule,
    extract_policy_rules,
    get_policy_summary,
    get_repeat_offender_summary,
    list_findings,
    list_policy_rules,
    list_violations,
    scan_transactions,
    test_draft_policy_rule,
    test_policy_rule,
    upload_policy_document_pdf,
    update_policy_rule,
)


def policy_check_transaction(transaction_id: str, reset_synthetic_evidence: bool = False) -> PolicyCheckResult:
    return check_transaction_policy(transaction_id, reset_synthetic_evidence)


def policy_scan_transactions(filters: PolicyScanRequest | None = None) -> PolicyScanSummary:
    return scan_transactions(filters)


def policy_get_summary() -> PolicyScanSummary:
    return get_policy_summary()


def policy_list_violations(
    severity: str | None = None,
    status: str | None = None,
    department_id: str | None = None,
) -> list[ViolationListItem]:
    return list_violations(severity=severity, status=status, department_id=department_id)


def policy_list_findings(
    severity: str | None = None,
    status: str | None = None,
    department_id: str | None = None,
) -> list[PolicyFindingItem]:
    return list_findings(severity=severity, status=status, department_id=department_id)


def policy_repeat_offenders() -> RepeatOffenderSummary:
    return get_repeat_offender_summary()


def policy_rules_list(limit: int = 50, offset: int = 0, status: str | None = None) -> list[PolicyRuleItem]:
    return list_policy_rules(limit=limit, offset=offset, status=status)


def policy_reset_data() -> PolicyResetResponse:
    return clear_policy_data()


def policy_rules_create(request: PolicyRuleWriteRequest) -> PolicyRuleItem:
    return create_policy_rule(request)


def policy_rules_update(rule_id: str, request: PolicyRulePatchRequest) -> PolicyRuleItem:
    return update_policy_rule(rule_id, request)


def policy_rules_test(rule_id: str, request: PolicyRuleTestRequest | None = None) -> PolicyRuleTestResponse:
    return test_policy_rule(rule_id, request)


def policy_rules_test_draft(request: PolicyRuleTestRequest) -> PolicyRuleTestResponse:
    return test_draft_policy_rule(request)


def policy_rules_extract(request: PolicyRuleExtractionRequest) -> PolicyRuleExtractionResponse:
    return extract_policy_rules(request)


def policy_documents_from_text(request: PolicyDocumentTextRequest) -> PolicyDocumentCreateResponse:
    return create_policy_document_from_text(request)


def policy_documents_upload(title: str | None, file_name: str, content_type: str | None, file_bytes: bytes) -> PolicyDocumentCreateResponse:
    return upload_policy_document_pdf(title, file_name, content_type, file_bytes)


def policy_documents_extract_rules(
    policy_document_id: str,
    request: PolicyDocumentExtractRequest | None = None,
) -> PolicyRuleExtractionResponse:
    return extract_policy_rules_for_document(policy_document_id, request)
