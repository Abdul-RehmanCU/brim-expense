from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from app.services.policy_service import run_policy_scan_and_refresh
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
from app.tools.policy_tools import (
    policy_check_transaction,
    policy_documents_extract_rules,
    policy_documents_from_text,
    policy_documents_upload,
    policy_get_summary,
    policy_list_findings,
    policy_list_violations,
    policy_reset_data,
    policy_repeat_offenders,
    policy_rules_create,
    policy_rules_extract,
    policy_rules_list,
    policy_rules_test,
    policy_rules_test_draft,
    policy_rules_update,
)

router = APIRouter(prefix="/policy", tags=["policy"])

AI_EXTRACTION_UPSTREAM_ERRORS = (
    "Claude returned invalid JSON for policy rule extraction.",
    "Claude rule extraction response must be a JSON object.",
    "OpenAI rule extraction response did not include parsed structured output.",
)


def extraction_http_exception(error: ValueError) -> HTTPException:
    detail = str(error)
    if detail.endswith("was not found."):
        return HTTPException(status_code=404, detail=detail)
    if detail in AI_EXTRACTION_UPSTREAM_ERRORS or detail.startswith("OpenAI structured policy rule extraction failed:"):
        return HTTPException(status_code=502, detail=detail)
    return HTTPException(status_code=400, detail=detail)


@router.post("/documents/from-text", response_model=PolicyDocumentCreateResponse)
def create_policy_document_from_text_route(request: PolicyDocumentTextRequest) -> PolicyDocumentCreateResponse:
    return policy_documents_from_text(request)


@router.post("/documents/upload", response_model=PolicyDocumentCreateResponse)
async def upload_policy_document_route(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
) -> PolicyDocumentCreateResponse:
    try:
        file_bytes = await file.read()
        return policy_documents_upload(title, file.filename or "policy.pdf", file.content_type, file_bytes)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/documents/{policy_document_id}/extract-rules", response_model=PolicyRuleExtractionResponse)
def extract_rules_for_document(
    policy_document_id: str,
    request: PolicyDocumentExtractRequest | None = None,
) -> PolicyRuleExtractionResponse:
    try:
        return policy_documents_extract_rules(policy_document_id, request)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise extraction_http_exception(error) from error


@router.get("/rules", response_model=list[PolicyRuleItem])
def list_rules(
    limit: int = Query(default=50, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
) -> list[PolicyRuleItem]:
    return policy_rules_list(limit=limit, offset=offset, status=status)


@router.delete("/reset", response_model=PolicyResetResponse)
def reset_policy_data() -> PolicyResetResponse:
    return policy_reset_data()


@router.post("/rules", response_model=PolicyRuleItem)
def create_rule(request: PolicyRuleWriteRequest) -> PolicyRuleItem:
    return policy_rules_create(request)


@router.patch("/rules/{rule_id}", response_model=PolicyRuleItem)
def update_rule(rule_id: str, request: PolicyRulePatchRequest) -> PolicyRuleItem:
    try:
        return policy_rules_update(rule_id, request)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/rules/{rule_id}/test", response_model=PolicyRuleTestResponse)
def test_rule(rule_id: str, request: PolicyRuleTestRequest | None = None) -> PolicyRuleTestResponse:
    try:
        return policy_rules_test(rule_id, request)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/rules/test-draft", response_model=PolicyRuleTestResponse)
def test_draft_rule(request: PolicyRuleTestRequest) -> PolicyRuleTestResponse:
    return policy_rules_test_draft(request)


@router.post("/rules/extract", response_model=PolicyRuleExtractionResponse)
def extract_rules(request: PolicyRuleExtractionRequest) -> PolicyRuleExtractionResponse:
    try:
        return policy_rules_extract(request)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise extraction_http_exception(error) from error


@router.post("/check/{transaction_id}", response_model=PolicyCheckResult)
def check_policy_for_transaction(
    transaction_id: str,
    reset_synthetic_evidence: bool = False,
) -> PolicyCheckResult:
    try:
        return policy_check_transaction(transaction_id, reset_synthetic_evidence)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/scan", response_model=PolicyScanSummary)
def scan_policy(request: PolicyScanRequest | None = None) -> PolicyScanSummary:
    return run_policy_scan_and_refresh(request or PolicyScanRequest())


@router.get("/summary", response_model=PolicyScanSummary)
def policy_summary() -> PolicyScanSummary:
    return policy_get_summary()


@router.get("/findings", response_model=list[PolicyFindingItem])
def policy_findings(
    severity: str | None = Query(default=None),
    status: str | None = Query(default=None),
    department_id: str | None = Query(default=None),
) -> list[PolicyFindingItem]:
    return policy_list_findings(severity=severity, status=status, department_id=department_id)


@router.get("/repeat-offenders", response_model=RepeatOffenderSummary)
def repeat_offenders() -> RepeatOffenderSummary:
    return policy_repeat_offenders()


@router.get("/violations", response_model=list[ViolationListItem])
def policy_violations(
    severity: str | None = Query(default=None),
    status: str | None = Query(default=None),
    department_id: str | None = Query(default=None),
) -> list[ViolationListItem]:
    return policy_list_violations(severity=severity, status=status, department_id=department_id)
