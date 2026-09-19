"""Tavily-backed discovery of sources that may later be imported as evidence."""

import json
import os
import re
import ssl
from abc import ABC, abstractmethod
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import certifi
from uuid import uuid4

from core.models import SourceRecommendation, SourceRecommendationResponse


class SourceSearchError(RuntimeError):
    """A source search could not be completed without exposing provider details."""


class SourceSearchProvider(ABC):
    @abstractmethod
    def search(self, query: str) -> list[dict[str, str]]:
        """Return provider results containing title, url, and snippet."""


class TavilySearchProvider(SourceSearchProvider):
    """Small direct client for Tavily's search endpoint; no result is invented."""

    endpoint = "https://api.tavily.com/search"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def search(self, query: str) -> list[dict[str, str]]:
        payload = json.dumps({"api_key": self.api_key, "query": query, "max_results": 5}).encode()
        request = Request(self.endpoint, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            with urlopen(request, timeout=10, context=ssl_context) as response:  # nosec B310: fixed HTTPS provider endpoint
                data = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            raise SourceSearchError("Tavily search is temporarily unavailable.") from error
        return [result for result in data.get("results", []) if isinstance(result, dict)]


def build_search_query(prompt: str) -> str:
    """Focus terse questions toward primary sources without an additional LLM call."""
    clean = " ".join(prompt.split()).strip().rstrip("?").strip()
    if not clean:
        return ""
    terms = clean.lower()
    if "google" in terms and any(word in terms for word in ("ceo", "leadership", "executive")):
        return "Google CEO official site:blog.google OR site:about.google OR site:abc.xyz"
    return clean if "official" in terms else f"{clean} official source"


def _is_official(domain: str, prompt: str) -> bool:
    """Conservative domain-based indicator, never inferred from a page title."""
    domain = domain.lower().removeprefix("www.")
    known_authorities = {
        "google": ("google.com", "about.google", "blog.google", "abc.xyz"), "salesforce": ("salesforce.com",),
        "python": ("python.org",), "pandas": ("pandas.pydata.org",),
        "openai": ("openai.com",), "fastapi": ("fastapi.tiangolo.com",),
        "eu ai act": ("europa.eu",),
    }
    text = prompt.lower()
    return any(entity in text and any(domain == root or domain.endswith("." + root) for root in roots)
               for entity, roots in known_authorities.items())


def recommend_sources(prompt: str) -> SourceRecommendationResponse:
    """Discover real URLs only; discovery results are not verifier input or evidence."""
    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        return SourceRecommendationResponse(
            available=False, status="unavailable",
            message="Web source recommendations are unavailable because TAVILY_API_KEY is not configured.",
        )
    try:
        results = TavilySearchProvider(api_key).search(build_search_query(prompt))
    except SourceSearchError:
        return SourceRecommendationResponse(available=False, status="unavailable", message="Source recommendations are temporarily unavailable.")
    recommendations: list[SourceRecommendation] = []
    seen_urls: set[str] = set()
    for result in results:
        url = str(result.get("url", "")).strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or url in seen_urls:
            continue
        seen_urls.add(url)
        domain = parsed.netloc.lower().removeprefix("www.")
        official = _is_official(domain, prompt)
        recommendations.append(SourceRecommendation(
            id=f"source_{uuid4().hex[:12]}", title=str(result.get("title") or domain), url=url,
            domain=domain, description=str(result.get("content") or result.get("snippet") or ""),
            relevance_reason="Official-domain source relevant to your prompt." if official else "Potentially relevant to your prompt.",
            is_official=official,
        ))
    recommendations.sort(key=lambda item: (-_relevance_score(item, prompt), item.title.lower()))
    return SourceRecommendationResponse(recommendations=recommendations)


def _relevance_score(item: SourceRecommendation, prompt: str) -> int:
    """Rank first-party and entity/topic matches ahead of incidental mentions."""
    terms = {term for term in re.findall(r"[a-z0-9]+", prompt.lower()) if term not in {"is", "the", "a", "an", "what", "who"}}
    haystack = f"{item.title} {item.description}".lower()
    score = sum(term in haystack for term in terms) * 10
    if item.is_official:
        score += 100
    if "ceo" in terms and "ceo" in haystack:
        score += 30
    if "leadership" in haystack:
        score += 10
    return score
