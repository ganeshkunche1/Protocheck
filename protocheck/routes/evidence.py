"""Thin HTTP API for adding, inspecting, and removing user evidence."""

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from core.models import EvidenceCollectionResponse, EvidenceItem, PastedEvidenceRequest, WebEvidenceRequest
from evidence.errors import EvidenceLoadError
from evidence.loader import load_pasted_text, load_uploaded_file, with_source_name
from evidence.processor import normalize_evidence
from evidence.store import EvidenceStore
from evidence.web_loader import load_webpage

router = APIRouter(prefix="/api/evidence", tags=["evidence"])
store = EvidenceStore()


@router.post("/text", response_model=EvidenceCollectionResponse, status_code=status.HTTP_201_CREATED)
async def add_pasted_evidence(request: PastedEvidenceRequest) -> EvidenceCollectionResponse:
    """Add user-pasted text to the current in-memory collection."""
    try:
        raw = load_pasted_text(request.content, request.source_name or "Pasted evidence")
        items = store.add_many(normalize_evidence(raw))
    except EvidenceLoadError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    return EvidenceCollectionResponse(items=items)


@router.post("/upload", response_model=EvidenceCollectionResponse, status_code=status.HTTP_201_CREATED)
async def upload_evidence(
    file: UploadFile = File(...), source_name: str | None = Form(default=None)
) -> EvidenceCollectionResponse:
    """Read an allowed upload in memory; the original file is not persisted."""
    content = await file.read()
    try:
        raw = with_source_name(load_uploaded_file(file.filename or "upload", content, file.content_type), source_name)
        items = store.add_many(normalize_evidence(raw))
    except EvidenceLoadError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    return EvidenceCollectionResponse(items=items)


@router.post("/web", response_model=EvidenceItem, status_code=status.HTTP_201_CREATED)
async def add_web_evidence(request: WebEvidenceRequest) -> EvidenceItem:
    """Retrieve one selected public webpage and add its actual text as evidence."""
    try:
        item = normalize_evidence([load_webpage(request.url, request.source_name)])[0]
        store.add_many([item])
        return item
    except EvidenceLoadError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"RETRIEVAL FAILED: {error}") from error


@router.get("", response_model=EvidenceCollectionResponse)
async def list_evidence() -> EvidenceCollectionResponse:
    """Return current evidence and provenance metadata."""
    return EvidenceCollectionResponse(items=store.list_all())


@router.delete("/{evidence_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_evidence(evidence_id: str) -> None:
    """Remove one item from memory without touching the user's original file."""
    if not store.remove(evidence_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence item was not found.")
