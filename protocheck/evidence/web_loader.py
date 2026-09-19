"""Small, bounded loader for an explicitly selected HTML webpage."""

import ipaddress
import socket
import ssl
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

import certifi

from core.models import EvidenceSourceType
from evidence.errors import EvidenceLoadError
from evidence.loader import RawEvidence

MAX_WEB_BYTES = 2 * 1024 * 1024
TIMEOUT_SECONDS = 10


class _ReadableTextParser(HTMLParser):
    """Extract visible textual content without executing or rendering a page."""

    _ignored = {"script", "style", "noscript", "svg", "nav", "footer", "header", "aside", "form"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._parts: list[str] = []
        self._ignored_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._ignored:
            self._ignored_depth += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in self._ignored and self._ignored_depth:
            self._ignored_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return
        if self._in_title:
            self.title = f"{self.title} {text}".strip()
        elif not self._ignored_depth:
            self._parts.append(text)

    @property
    def content(self) -> str:
        return "\n".join(self._parts)


def load_webpage(url: str, source_name: str | None = None) -> RawEvidence:
    """Fetch one public HTML URL and return only its extracted text as evidence."""
    _validate_public_url(url)
    request = Request(url, headers={"User-Agent": "ProtoCheck/0.1 evidence retrieval", "Accept": "text/html,application/xhtml+xml"})
    opener = build_opener(_SafeRedirectHandler(), _HttpsHandler())
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            final_url = response.geturl()
            _validate_public_url(final_url)
            mime_type = response.headers.get_content_type()
            if mime_type not in {"text/html", "application/xhtml+xml"}:
                raise EvidenceLoadError("The selected URL did not return an HTML webpage.")
            data = response.read(MAX_WEB_BYTES + 1)
    except HTTPError as error:
        raise EvidenceLoadError(f"The webpage returned HTTP {error.code}.") from error
    except (URLError, TimeoutError, OSError) as error:
        raise EvidenceLoadError("The webpage could not be retrieved.") from error
    if len(data) > MAX_WEB_BYTES:
        raise EvidenceLoadError("The webpage exceeds the 2 MB retrieval limit.")
    charset = response.headers.get_content_charset() or "utf-8"
    parser = _ReadableTextParser()
    parser.feed(data.decode(charset, errors="replace"))
    content = parser.content.strip()
    if not content:
        raise EvidenceLoadError("The webpage contains no readable text.")
    parsed = urlparse(final_url)
    title = parser.title or parsed.netloc
    return RawEvidence(source_name=(source_name or title).strip(), source_type=EvidenceSourceType.WEB,
                       content=content, mime_type=mime_type, url=final_url, domain=parsed.netloc.lower(),
                       title=title, retrieval_status="AVAILABLE_AS_EVIDENCE")


def _validate_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise EvidenceLoadError("Provide a valid public HTTP or HTTPS URL.")
    try:
        addresses = {result[4][0] for result in socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)}
    except socket.gaierror as error:
        raise EvidenceLoadError("The webpage host could not be resolved.") from error
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise EvidenceLoadError("Only public webpage URLs can be retrieved.")


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        _validate_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _HttpsHandler(HTTPSHandler):
    def __init__(self) -> None:
        super().__init__(context=ssl.create_default_context(cafile=certifi.where()))
