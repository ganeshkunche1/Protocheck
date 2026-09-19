"""Routes for evidence-bounded verification and future repair."""

from fastapi import APIRouter, HTTPException, status

from core.models import FinalResponse, RepairRequest, VerificationReport, VerificationRequest
from core.repair import RepairError, repair_and_reverify
from core.verifier import VerificationError, verify_claims

router = APIRouter(prefix="/api")


@router.post("/verify", response_model=VerificationReport)
async def verify(request: VerificationRequest) -> VerificationReport:
    """Verify extracted claims only against the supplied selected evidence."""
    try:
        return verify_claims(request.claims, request.selected_evidence)
    except VerificationError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error


@router.post("/repair", response_model=FinalResponse)
async def repair(request: RepairRequest) -> FinalResponse:
    """Repair against selected evidence, then re-extract and re-verify all claims."""
    try:
        return repair_and_reverify(request)
    except RepairError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
