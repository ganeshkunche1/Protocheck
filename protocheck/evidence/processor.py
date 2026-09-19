"""Conservative, deterministic normalization of loaded evidence."""

from uuid import uuid4

from core.models import EvidenceItem
from evidence.loader import RawEvidence


def normalize_evidence(items: list[RawEvidence]) -> list[EvidenceItem]:
    """Create common evidence records without paraphrasing or summarizing content."""
    return [normalize_item(item) for item in items]


def normalize_item(item: RawEvidence) -> EvidenceItem:
    """Normalize only line endings while preserving all meaningful content."""
    content = item.content.replace("\r\n", "\n").replace("\r", "\n")
    return EvidenceItem(
        id=f"evidence_{uuid4().hex}",
        source_name=item.source_name.strip() or "Untitled evidence",
        source_type=item.source_type,
        content=content,
        file_name=item.file_name,
        page_number=item.page_number,
        mime_type=item.mime_type,
        url=item.url,
        domain=item.domain,
        title=item.title,
        retrieval_status=item.retrieval_status,
        character_count=len(content),
    )
