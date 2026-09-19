"""Stage 4 tests for deterministic, evidence-bounded verification."""

import pytest

from core.claim_extractor import extract_claims
from core.models import Claim, ClaimType, EvidenceItem, EvidenceSourceType, VerificationVerdict
from core.verifier import VerificationError, validate_verifier_decision, verify_claim, verify_claims


def claim(text: str, identifier: str = "claim_001") -> Claim:
    return Claim(id=identifier, text=text, source_sentence=text, claim_type=ClaimType.FACTUAL)


def evidence(content: str, identifier: str = "evidence_001", page: int | None = None) -> EvidenceItem:
    return EvidenceItem(id=identifier, source_name="Selected source", source_type=EvidenceSourceType.PASTED_TEXT, content=content, page_number=page, character_count=len(content))


def test_explicit_evidence_supports_a_claim() -> None:
    result = verify_claim(claim("Company X was founded in 2019."), [evidence("Company X was founded in 2019.")])
    assert result.verdict is VerificationVerdict.SUPPORTED
    assert result.evidence[0].relevant_excerpt == "Company X was founded in 2019."


def test_ceo_identity_supports_reversed_official_wording() -> None:
    result = verify_claim(claim("The CEO of Google is Sundar Pichai."), [evidence("Sundar Pichai is the CEO of Google and Alphabet.")])
    assert result.verdict is VerificationVerdict.SUPPORTED


def test_different_ceo_identity_is_contradicted() -> None:
    result = verify_claim(claim("The CEO of Google is Sundar Pichai."), [evidence("The CEO of Google is Example Person.")])
    assert result.verdict is VerificationVerdict.CONTRADICTED


def test_ceo_identity_with_different_person_is_contradicted_in_reverse_word_order() -> None:
    result = verify_claim(claim("The CEO of Google is Sundar Pichai."), [evidence("Sam Altman is the CEO of Google.")])
    assert result.verdict is VerificationVerdict.CONTRADICTED


def test_explicit_conflict_is_contradicted() -> None:
    result = verify_claim(claim("Product X launched in 2020."), [evidence("Product X launched in March 2021.")])
    assert result.verdict is VerificationVerdict.CONTRADICTED


def test_unmentioned_claim_is_unsupported() -> None:
    result = verify_claim(claim("Company X was founded by Alice."), [evidence("Company X was established in 2019.")])
    assert result.verdict is VerificationVerdict.UNSUPPORTED


def test_partial_support_is_not_marked_supported() -> None:
    result = verify_claim(claim("Company X was founded in 2019 by Alice Smith."), [evidence("Company X was founded in 2019.")])
    assert result.verdict is VerificationVerdict.UNSUPPORTED


def test_entity_mismatch_is_contradicted() -> None:
    result = verify_claim(claim("Company B acquired Product X."), [evidence("Company A acquired Product X.")])
    assert result.verdict is VerificationVerdict.CONTRADICTED


def test_deterministic_numeric_mismatch_is_contradicted() -> None:
    result = verify_claim(claim("Revenue increased by 42%."), [evidence("Revenue increased from ₹10 million to ₹12 million.")])
    assert result.verdict is VerificationVerdict.CONTRADICTED
    assert "20%" in result.reason


def test_date_mismatch_is_contradicted() -> None:
    assert verify_claim(claim("Product X launched in 2020."), [evidence("Product X launched in March 2021.")]).verdict is VerificationVerdict.CONTRADICTED


def test_no_evidence_is_never_supported() -> None:
    result = verify_claim(claim("Company X was founded in 2019."), [])
    assert result.verdict is VerificationVerdict.UNSUPPORTED
    assert "No selected evidence" in result.reason


def test_invalid_evidence_reference_is_rejected() -> None:
    selected = evidence("Company X was founded in 2019.")
    with pytest.raises(VerificationError, match="evidence ID"):
        validate_verifier_decision({"claim_id": "claim_001", "verdict": "SUPPORTED", "reason": "Claim is stated.", "evidence": [{"evidence_id": "evidence_999", "source_name": "Selected source", "page_number": None, "relevant_excerpt": "Company X was founded in 2019."}]}, claim("Company X was founded in 2019."), [selected])


def test_invalid_verdict_is_rejected() -> None:
    with pytest.raises(VerificationError, match="malformed"):
        validate_verifier_decision({"claim_id": "claim_001", "verdict": "MAYBE", "reason": "Unknown."}, claim("Company X was founded in 2019."), [])


def test_multiple_claims_keep_mixed_results_independent() -> None:
    report = verify_claims([claim("Company X was founded in 2019.", "claim_001"), claim("Company X was founded by Alice.", "claim_002"), claim("Product X launched in 2020.", "claim_003")], [evidence("Company X was founded in 2019. Product X launched in 2021.")])
    assert [result.verdict for result in report.claims] == [VerificationVerdict.SUPPORTED, VerificationVerdict.UNSUPPORTED, VerificationVerdict.CONTRADICTED]
    assert report.supported_count == report.unsupported_count == report.contradicted_count == 1


def test_related_but_insufficient_evidence_is_not_accepted() -> None:
    result = verify_claim(claim("Alice Smith founded Company X."), [evidence("Alice Smith became CEO of Company X in 2021.")])
    assert result.verdict is VerificationVerdict.UNSUPPORTED


def test_assignment_demonstration_only_supports_the_established_year() -> None:
    claims = extract_claims("Company X was established in 2019 by Alice Smith.")
    report = verify_claims(claims, [evidence("Company X was established in 2019.")])
    assert [item.verdict for item in report.claims] == [VerificationVerdict.SUPPORTED, VerificationVerdict.UNSUPPORTED]
