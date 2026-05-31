from app.schemas.approvals import ApprovalDecisionRequest, ApprovalListResponse, ApprovalRequestCreate, ApprovalRequestDetail
from app.schemas.common import PlaceholderResponse
from app.services.approvals_service import (
    create_approval_request,
    decide_approval,
    get_approvals_status,
    list_approvals,
)


def approval_status() -> PlaceholderResponse:
    return get_approvals_status()


def approval_create_request(request: ApprovalRequestCreate) -> ApprovalRequestDetail:
    return create_approval_request(request)


def approval_decide(approval_id: str, request: ApprovalDecisionRequest) -> ApprovalRequestDetail:
    return decide_approval(approval_id, request)


def approval_list(status: str | None = None, limit: int = 100) -> ApprovalListResponse:
    return list_approvals(status=status, limit=limit)

