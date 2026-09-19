"""HTTP endpoint for draft-only atomic claim extraction."""

from fastapi import APIRouter, HTTPException, status

from core.claim_extractor import ClaimExtractionError, extract_claims
from core.models import ClaimExtractionRequest, ClaimExtractionResponse

router = APIRouter(prefix="/api/claims", tags=["claims"])


@router.post("/extract", response_model=ClaimExtractionResponse)
async def extract(request: ClaimExtractionRequest) -> ClaimExtractionResponse:
    """Extract claims from a draft without consulting evidence or deciding truth."""
    try:
        return ClaimExtractionResponse(claims=extract_claims(request.draft_answer))
    except ClaimExtractionError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
