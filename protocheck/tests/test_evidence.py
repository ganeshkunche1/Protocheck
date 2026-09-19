"""Deterministic Stage 2 tests for user-provided evidence ingestion."""

from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from core.models import EvidenceSourceType
from evidence.errors import EvidenceLoadError, UnsupportedEvidenceTypeError
from evidence.loader import load_pdf_file, load_pasted_text, load_text_file, load_uploaded_file
from evidence.processor import normalize_evidence
from evidence.store import EvidenceStore


def make_text_pdf(path: Path) -> None:
    """Create a minimal text-based PDF without an external fixture dependency."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
    content = DecodedStreamObject()
    content.set_data(b"BT /F1 12 Tf 72 720 Td (PDF source evidence) Tj ET")
    page[NameObject("/Contents")] = content
    with path.open("wb") as handle:
        writer.write(handle)


def test_pasted_text_becomes_a_valid_evidence_item() -> None:
    item = normalize_evidence(load_pasted_text("The launch date is 2024.", "Release notes"))[0]
    assert item.source_type is EvidenceSourceType.PASTED_TEXT
    assert item.source_name == "Release notes"
    assert item.character_count == len(item.content)


def test_txt_file_loads_and_preserves_content(tmp_path: Path) -> None:
    text_file = tmp_path / "facts.txt"
    text_file.write_text("Ada Lovelace\r\nwas a mathematician.", encoding="utf-8")
    item = normalize_evidence(load_text_file(text_file))[0]
    assert item.source_type is EvidenceSourceType.TXT
    assert item.file_name == "facts.txt"
    assert item.content == "Ada Lovelace\nwas a mathematician."


def test_pdf_text_is_extracted_with_page_provenance(tmp_path: Path) -> None:
    pdf_file = tmp_path / "paper.pdf"
    make_text_pdf(pdf_file)
    item = normalize_evidence(load_pdf_file(pdf_file))[0]
    assert "PDF source evidence" in item.content
    assert item.source_type is EvidenceSourceType.PDF
    assert item.page_number == 1
    assert item.file_name == "paper.pdf"


def test_empty_txt_is_rejected() -> None:
    with pytest.raises(EvidenceLoadError, match="empty"):
        load_uploaded_file("empty.txt", b"", "text/plain")


def test_unsupported_file_type_is_rejected() -> None:
    with pytest.raises(UnsupportedEvidenceTypeError):
        load_uploaded_file("notes.docx", b"content", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")


def test_malformed_pdf_is_handled_gracefully() -> None:
    with pytest.raises(EvidenceLoadError, match="could not be read"):
        load_uploaded_file("broken.pdf", b"not a PDF", "application/pdf")


def test_multiple_items_can_coexist_and_removal_is_isolated() -> None:
    items = normalize_evidence(load_pasted_text("First", "One") + load_pasted_text("Second", "Two"))
    store = EvidenceStore()
    store.add_many(items)
    assert store.remove(items[0].id) is True
    assert [item.source_name for item in store.list_all()] == ["Two"]


def test_metadata_is_preserved() -> None:
    item = normalize_evidence(load_uploaded_file("facts.txt", b"Facts", "text/plain"))[0]
    assert item.file_name == "facts.txt"
    assert item.mime_type == "text/plain"
    assert item.character_count == 5


def test_normalization_does_not_semantically_change_content() -> None:
    original = "Price: $10\r\nDate: 2026-01-02\rName: M\u00fcller"
    item = normalize_evidence(load_pasted_text(original))[0]
    assert item.content == "Price: $10\nDate: 2026-01-02\nName: M\u00fcller"
