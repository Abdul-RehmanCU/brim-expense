from fastapi import APIRouter

from app.schemas.common import PlaceholderResponse
from app.services.ai_service import get_ai_status
from app.services.rag_service import get_rag_status

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/status", response_model=PlaceholderResponse)
def ai_status() -> PlaceholderResponse:
    return get_ai_status()


@router.get("/rag/status", response_model=PlaceholderResponse)
def rag_status() -> PlaceholderResponse:
    return get_rag_status()
