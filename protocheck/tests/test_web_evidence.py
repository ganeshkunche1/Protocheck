"""Web evidence is real retrieved content, never a recommendation snippet."""

import pytest

from core.claim_extractor import extract_claims
from core.models import EvidenceSourceType
from core.verifier import verify_claims
from evidence.errors import EvidenceLoadError
from evidence.processor import normalize_evidence
from evidence.web_loader import load_webpage


def test_selected_webpage_becomes_web_evidence(monkeypatch) -> None:
    class Response:
        headers = type("Headers", (), {"get_content_type": lambda self: "text/html", "get_content_charset": lambda self: "utf-8"})()
        def geturl(self): return "https://example.com/leadership"
        def read(self, _limit): return b"<html><head><title>Leadership</title></head><body><nav>Menu</nav><main>The CEO of Google is Sundar Pichai.</main></body></html>"
        def __enter__(self): return self
        def __exit__(self, *_args): return False
    monkeypatch.setattr("evidence.web_loader._validate_public_url", lambda _url: None)
    monkeypatch.setattr("evidence.web_loader.build_opener", lambda *_args: type("Opener", (), {"open": lambda self, *_args, **_kwargs: Response()})())
    item = normalize_evidence([load_webpage("https://example.com/leadership")])[0]
    assert item.source_type is EvidenceSourceType.WEB
    assert item.url == "https://example.com/leadership"
    assert item.title == "Leadership"
    assert "Menu" not in item.content
    assert item.content == "The CEO of Google is Sundar Pichai."
    report = verify_claims(extract_claims("The CEO of Google is Sundar Pichai."), [item])
    assert report.supported_count == 1


def test_failed_retrieval_never_creates_evidence(monkeypatch) -> None:
    monkeypatch.setattr("evidence.web_loader._validate_public_url", lambda _url: (_ for _ in ()).throw(EvidenceLoadError("Only public webpage URLs can be retrieved.")))
    with pytest.raises(EvidenceLoadError):
        load_webpage("http://127.0.0.1/private")
