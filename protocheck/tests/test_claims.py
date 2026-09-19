"""Deterministic Stage 3 tests for atomic claim extraction."""

import pytest

from core.claim_extractor import ClaimExtractionError, extract_claims
from core.models import ClaimType


def texts(answer: str) -> list[str]:
    return [claim.text for claim in extract_claims(answer)]


def test_extracts_one_simple_factual_claim() -> None:
    claims = extract_claims("Company X was founded in 2019.")
    assert len(claims) == 1
    assert claims[0].text == "Company X was founded in 2019."
    assert claims[0].id == "claim_001"


def test_splits_multiple_independent_claims() -> None:
    assert texts("Tesla was founded in 2003, is headquartered in Texas, and produces electric vehicles.") == [
        "Tesla was founded in 2003.",
        "Tesla is headquartered in Texas.",
        "Tesla produces electric vehicles.",
    ]


def test_splits_compound_platform_claims() -> None:
    assert texts("Google Maps launched in 2005 and is available on Android and iOS.") == [
        "Google Maps launched in 2005.",
        "Google Maps is available on Android.",
        "Google Maps is available on iOS.",
    ]


def test_preserves_numerical_and_date_claims() -> None:
    numerical = extract_claims("Revenue increased by 42%.")[0]
    temporal = extract_claims("The product launched in March 2025.")[0]
    assert numerical.text == "Revenue increased by 42%."
    assert numerical.claim_type is ClaimType.NUMERICAL
    assert temporal.text == "The product launched in March 2025."
    assert temporal.claim_type is ClaimType.TEMPORAL


def test_conversational_response_has_no_claims() -> None:
    assert extract_claims("Hello! How can I help you?") == []


def test_conservative_duplicate_removal() -> None:
    assert texts("Company X was founded in 2019. The company was established in 2019.") == ["Company X was founded in 2019."]


def test_claim_preserves_source_sentence() -> None:
    source = "Google Maps launched in 2005 and is available on Android and iOS."
    assert all(claim.source_sentence == source for claim in extract_claims(source))


def test_extractor_never_invents_a_founder() -> None:
    claims = texts("Company X was founded in 2019.")
    assert all("Alice" not in claim and "Smith" not in claim for claim in claims)


def test_empty_draft_fails_safely() -> None:
    with pytest.raises(ClaimExtractionError, match="empty"):
        extract_claims("   ")


def test_founder_and_year_are_independently_atomic() -> None:
    assert texts("Company X was founded in 2019 by Alice Smith.") == [
        "Company X was founded in 2019.",
        "Alice Smith was one of Company X's founders.",
    ]


def test_rejects_headings_meta_text_and_incomplete_clauses() -> None:
    assert texts("# Common possibilities\nHere are the options:\nBecause Company X is a placeholder\nCompany X was founded in 2019.") == [
        "Company X was founded in 2019."
    ]


def test_splits_each_named_founder_without_inventing_facts() -> None:
    assert texts("Twitter was founded on March 21, 2006 by Jack Dorsey, Evan Williams, Biz Stone, and Noah Glass.") == [
        "Twitter was founded on March 21, 2006.",
        "Jack Dorsey was one of Twitter's founders.",
        "Evan Williams was one of Twitter's founders.",
        "Biz Stone was one of Twitter's founders.",
        "Noah Glass was one of Twitter's founders.",
    ]


def test_compound_timeline_claims_are_atomic_and_pronouns_are_self_contained() -> None:
    assert texts("The CEO of Google is Sundar Pichai. He has been serving as Google's CEO since August 2015, and in December 2019, he also became the CEO of Alphabet Inc.") == [
        "The CEO of Google is Sundar Pichai.",
        "Sundar Pichai has been serving as Google's CEO since August 2015.",
        "Sundar Pichai became the CEO of Alphabet Inc in December 2019.",
    ]


def test_splits_two_independent_predicates_with_the_shared_subject() -> None:
    assert texts("Alice became CEO in 2020 and joined the company in 2018.") == [
        "Alice became CEO in 2020.", "Alice joined the company in 2018."
    ]
