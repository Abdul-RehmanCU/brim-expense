from fastapi import APIRouter, Query

from app.schemas.review_queue import ReviewQueueItem, ReviewQueueRefreshRequest, ReviewQueueRefreshResponse
from app.services.review_queue_service import list_review_queue, refresh_review_queue

router = APIRouter(prefix="/review-queue", tags=["review-queue"])


@router.post("/refresh", response_model=ReviewQueueRefreshResponse)
def refresh_review_queue_route(request: ReviewQueueRefreshRequest | None = None) -> ReviewQueueRefreshResponse:
    return refresh_review_queue(request or ReviewQueueRefreshRequest())


@router.get("/items", response_model=list[ReviewQueueItem])
def review_queue_items(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    queue_status: str = Query(default="open"),
    review_level: str | None = Query(default=None),
    policy_status: str | None = Query(default=None),
) -> list[ReviewQueueItem]:
    return list_review_queue(
        limit=limit,
        offset=offset,
        queue_status=queue_status,
        review_level=review_level,
        policy_status=policy_status,
    )
