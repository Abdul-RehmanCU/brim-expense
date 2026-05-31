from fastapi import APIRouter, Query

from app.schemas.approvals import (
    ApprovalExplanation,
    ApprovalDecisionRequest,
    ApprovalListResponse,
    ApprovalRequestCreate,
    ApprovalRequestDetail,
)
from app.schemas.common import PlaceholderResponse
from app.services.approvals_service import (
    create_approval_request,
    decide_approval,
    get_approval,
    get_approval_explanation,
    get_approvals_status,
    list_approvals,
)

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("/status", response_model=PlaceholderResponse)
def approvals_status() -> PlaceholderResponse:
    return get_approvals_status()


@router.get("", response_model=ApprovalListResponse)
def approvals_list(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> ApprovalListResponse:
    return list_approvals(status=status, limit=limit, offset=offset)


@router.post("", response_model=ApprovalRequestDetail)
def approvals_create(request: ApprovalRequestCreate) -> ApprovalRequestDetail:
    return create_approval_request(request)


@router.get("/{approval_id}", response_model=ApprovalRequestDetail)
def approvals_detail(approval_id: str) -> ApprovalRequestDetail:
    return get_approval(approval_id)


@router.get("/{approval_id}/explanation", response_model=ApprovalExplanation)
def approvals_explanation(approval_id: str) -> ApprovalExplanation:
    return get_approval_explanation(approval_id)


@router.post("/{approval_id}/decision", response_model=ApprovalRequestDetail)
def approvals_decide(approval_id: str, request: ApprovalDecisionRequest) -> ApprovalRequestDetail:
    return decide_approval(approval_id, request)
