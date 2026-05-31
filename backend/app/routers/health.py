from fastapi import APIRouter, Response

from app.schemas.common import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/", response_model=HealthResponse)
def root() -> HealthResponse:
    return HealthResponse(status="ok", service="brim-expense-copilot-backend")


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="brim-expense-copilot-backend")


@router.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)
