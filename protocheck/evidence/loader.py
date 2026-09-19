"""Source-specific, non-semantic extraction of user-provided evidence."""

from dataclasses import dataclass, replace
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from core.models import EvidenceSourceType
from evidence.errors import EvidenceLoadError, UnsupportedEvidenceTypeError

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class RawEvidence:
    """Extracted source content before deterministic normalization."""

    source_name: str
    source_type: EvidenceSourceType
    content: str
    file_name: str | None = None
    page_number: int | None = None
    mime_type: str | None = None
    url: str | None = None
    domain: str | None = None
    title: str | None = None
    retrieval_status: str | None = None


def load_pasted_text(content: str, source_name: str = "Pasted evidence") -> list[RawEvidence]:
    """Accept pasted evidence without interpreting its meaning."""
    _require_content(content, "Pasted evidence is empty.")
    return [RawEvidence(source_name, EvidenceSourceType.PASTED_TEXT, content)]


def load_text_file(path: Path) -> list[RawEvidence]:
    """Read a TXT file for local, programmatic use."""
    return load_uploaded_file(path.name, path.read_bytes(), "text/plain")


def load_pdf_file(path: Path) -> list[RawEvidence]:
    """Extract readable text from a local PDF while retaining page provenance."""
    return load_uploaded_file(path.name, path.read_bytes(), "application/pdf")


def load_uploaded_file(file_name: str, content: bytes, mime_type: str | None) -> list[RawEvidence]:
    """Validate and extract an uploaded TXT or text-based PDF from memory."""
    _validate_upload(file_name, content, mime_type)
    if Path(file_name).suffix.lower() == ".txt":
        return [_load_text_bytes(file_name, content, mime_type)]
    return _load_pdf_bytes(file_name, content, mime_type)


def with_source_name(items: list[RawEvidence], source_name: str | None) -> list[RawEvidence]:
    """Apply an optional user-friendly label without altering source content."""
    return [replace(item, source_name=source_name.strip()) for item in items] if source_name and source_name.strip() else items


def _validate_upload(file_name: str, content: bytes, mime_type: str | None) -> None:
    suffix = Path(file_name).suffix.lower()
    if suffix not in {".txt", ".pdf"}:
        raise UnsupportedEvidenceTypeError("Only TXT and PDF evidence files are supported.")
    if not content:
        raise EvidenceLoadError("The uploaded file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise EvidenceLoadError("The uploaded file exceeds the 10 MB evidence limit.")
    allowed = {".txt": {"text/plain", "application/octet-stream", None}, ".pdf": {"application/pdf", "application/octet-stream", None}}
    if mime_type not in allowed[suffix]:
        raise UnsupportedEvidenceTypeError("The uploaded file type does not match its supported extension.")


def _load_text_bytes(file_name: str, content: bytes, mime_type: str | None) -> RawEvidence:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("utf-8", errors="replace")
    _require_content(text, "The TXT file contains no readable text.")
    return RawEvidence(file_name, EvidenceSourceType.TXT, text, file_name, None, mime_type or "text/plain")


def _load_pdf_bytes(file_name: str, content: bytes, mime_type: str | None) -> list[RawEvidence]:
    try:
        reader = PdfReader(BytesIO(content))
    except (PdfReadError, ValueError, OSError) as error:
        raise EvidenceLoadError("The PDF could not be read. Please upload a valid PDF file.") from error
    if not reader.pages:
        raise EvidenceLoadError("The PDF contains no pages.")
    pages: list[RawEvidence] = []
    try:
        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            pages.append(RawEvidence(file_name, EvidenceSourceType.PDF, text, file_name, page_number, mime_type or "application/pdf"))
    except (PdfReadError, ValueError, OSError) as error:
        raise EvidenceLoadError("Text could not be extracted from this PDF.") from error
    if not any(page.content.strip() for page in pages):
        raise EvidenceLoadError("PDF contains no extractable text. OCR is not enabled in this stage.")
    return pages


def _require_content(content: str, message: str) -> None:
    if not content or not content.strip():
        raise EvidenceLoadError(message)
