"""Source recommendations must remain distinct from imported evidence."""

from core.source_recommender import build_search_query, recommend_sources


def test_unconfigured_search_is_explicitly_unavailable(monkeypatch) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    response = recommend_sources("How do I add location in Google Mail?")
    assert response.available is False
    assert response.status == "unavailable"
    assert response.recommendations == []
    assert "TAVILY_API_KEY" in (response.message or "")


def test_tavily_results_are_real_urls_and_official_domains_rank_first(monkeypatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    monkeypatch.setattr("core.source_recommender.TavilySearchProvider.search", lambda _self, _query: [
        {"title": "News", "url": "https://example.com/google-ceo", "content": "Secondary coverage"},
        {"title": "Google leadership", "url": "https://about.google/company-info/", "content": "Company leadership"},
    ])
    response = recommend_sources("google ceo is?")
    assert response.available is True
    assert [item.domain for item in response.recommendations] == ["about.google", "example.com"]
    assert response.recommendations[0].is_official is True
    assert all(item.retrieval_status == "NOT_RETRIEVED" for item in response.recommendations)


def test_query_builder_is_focused_without_an_llm() -> None:
    assert build_search_query("google ceo is ?") == "Google CEO official site:blog.google OR site:about.google OR site:abc.xyz"
