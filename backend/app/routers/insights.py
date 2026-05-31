from fastapi import APIRouter, HTTPException, Query, Response

from app.schemas.insights import (
    InsightArtifactRequest,
    InsightArtifactType,
    InsightPlanRequest,
    InsightPlanResponse,
    InsightQueryRequest,
    InsightQueryResponse,
    InsightSession,
    InsightSessionCreateRequest,
    InsightSessionDetail,
)
from app.services.insight_artifact_service import build_insight_artifact, build_session_artifact
from app.services.insights_service import (
    create_insight_plan,
    create_insight_session,
    get_insight_session,
    list_insight_sessions,
    query_insights,
)

router = APIRouter(prefix="/insights", tags=["insights"])


@router.post("/sessions", response_model=InsightSessionDetail)
def create_session(request: InsightSessionCreateRequest | None = None) -> InsightSessionDetail:
    session = create_insight_session(request or InsightSessionCreateRequest())
    return get_insight_session(session.id)


@router.get("/sessions", response_model=list[InsightSession])
def list_sessions(limit: int = Query(default=40, ge=1, le=100)) -> list[InsightSession]:
    return list_insight_sessions(limit=limit)


@router.get("/sessions/{session_id}", response_model=InsightSessionDetail)
def get_session(session_id: str) -> InsightSessionDetail:
    return get_insight_session(session_id)


@router.post("/plan", response_model=InsightPlanResponse)
def plan_insight(request: InsightPlanRequest) -> InsightPlanResponse:
    return create_insight_plan(request)


@router.post("/query", response_model=InsightQueryResponse)
def query_insight(request: InsightQueryRequest) -> InsightQueryResponse:
    try:
        return query_insights(request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/artifacts/{artifact_type}")
def generate_artifact(artifact_type: InsightArtifactType, request: InsightArtifactRequest) -> Response:
    content, file_name, media_type = build_insight_artifact(request.result, artifact_type)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@router.get("/sessions/{session_id}/artifacts/{artifact_type}")
def download_session_artifact(session_id: str, artifact_type: InsightArtifactType) -> Response:
    content, file_name, media_type = build_session_artifact(session_id, artifact_type)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@router.get("/sessions/{session_id}/messages/{message_id}/artifacts/{artifact_type}")
def download_message_artifact(session_id: str, message_id: str, artifact_type: InsightArtifactType) -> Response:
    content, file_name, media_type = build_session_artifact(session_id, artifact_type, message_id=message_id)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )
