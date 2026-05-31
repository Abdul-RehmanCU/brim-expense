from fastapi import APIRouter

from app.schemas.data_quality import DataQualityValidationRequest, DataQualityValidationResponse
from app.schemas.transactions import (
    TransactionImportRequest,
    TransactionImportResponse,
    TransactionEnrichmentRequest,
    TransactionEnrichmentResponse,
    TransactionResetResponse,
    TransactionsSummaryResponse,
)
from app.services.transactions_service import (
    clear_transactions,
    enrich_transactions,
    get_transactions_summary,
    import_transactions,
    validate_transaction_data_quality,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("/summary", response_model=TransactionsSummaryResponse)
def transactions_summary() -> TransactionsSummaryResponse:
    return get_transactions_summary()


@router.post("/enrich-existing", response_model=TransactionEnrichmentResponse)
def enrich_existing_transactions(request: TransactionEnrichmentRequest | None = None) -> TransactionEnrichmentResponse:
    return enrich_transactions(request or TransactionEnrichmentRequest())


@router.post("/data-quality", response_model=DataQualityValidationResponse)
def validate_data_quality(request: DataQualityValidationRequest) -> DataQualityValidationResponse:
    return validate_transaction_data_quality(request)


@router.post("/import", response_model=TransactionImportResponse)
def import_transactions_route(request: TransactionImportRequest) -> TransactionImportResponse:
    return import_transactions(request)


@router.delete("/reset", response_model=TransactionResetResponse)
def reset_transactions() -> TransactionResetResponse:
    return clear_transactions()
