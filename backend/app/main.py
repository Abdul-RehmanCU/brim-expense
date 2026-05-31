from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import ai, approvals, health, insights, policy, reports, review_queue, risk, transactions


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="PolyPilot Backend",
        version="0.1.0",
        description="Python API boundary for PolyPilot backend business logic.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(transactions.router)
    app.include_router(policy.router)
    app.include_router(risk.router)
    app.include_router(review_queue.router)
    app.include_router(ai.router)
    app.include_router(insights.router)
    app.include_router(approvals.router)
    app.include_router(reports.router)

    return app


app = create_app()
