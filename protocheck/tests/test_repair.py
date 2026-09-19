"""Stage 5 tests for constrained repair and mandatory re-verification."""

from collections.abc import Callable

from core.claim_extractor import extract_claims
from core.models import EvidenceItem, EvidenceSourceType, RepairRequest, RepairStatus, VerificationVerdict
from core.repair import build_repair_context, repair_and_reverify
from core.verifier import verify_claims


def selected(content: str) -> list[EvidenceItem]:
    return [EvidenceItem(id="evidence_001", source_name="Official record", source_type=EvidenceSourceType.PASTED_TEXT, content=content, character_count=len(content))]


def request(draft: str, evidence: list[EvidenceItem]) -> RepairRequest:
    claims = extract_claims(draft)
    return RepairRequest(original_prompt="Tell me about Company X.", original_draft=draft, claims=claims, verification_report=verify_claims(claims, evidence), selected_evidence=evidence)


def repair_with(answer: str) -> Callable[[str], str]:
    return lambda context: answer


def test_repair_removes_unsupported_claim_and_reverification_passes() -> None:
    item = request("Company X was founded in 2019 by Alice Smith.", selected("Company X was founded in 2019."))
    response = repair_and_reverify(item, repair_with("Company X was founded in 2019."))
    assert response.original_draft == item.original_draft
    assert response.repaired_verification is not None
    assert response.repaired_verification.status.value == "PASSED"
    assert response.repair_summary.removed_claims == 1


def test_repair_corrects_a_contradicted_claim_from_evidence() -> None:
    item = request("Product X launched in 2020.", selected("Product X launched in 2021."))
    response = repair_and_reverify(item, repair_with("Product X launched in 2021."))
    assert response.repaired_verification is not None
    assert response.repaired_verification.claims[0].verdict is VerificationVerdict.SUPPORTED
    assert response.repair_summary.status is RepairStatus.FIXED


def test_new_unsupported_claim_is_detected_after_repair() -> None:
    item = request("Company X was founded by Alice.", selected("Company X was founded in 2019."))
    response = repair_and_reverify(item, repair_with("Company X was founded in 2019. It has 10 million users."))
    assert response.repaired_verification is not None
    assert any(result.verdict is VerificationVerdict.UNSUPPORTED for result in response.repaired_verification.claims)
    assert response.repair_summary.new_failed_claims == 1


def test_new_contradicted_claim_is_detected_after_repair() -> None:
    item = request("Company X was founded by Alice.", selected("Company X was founded in 2019. Product X launched in 2021."))
    response = repair_and_reverify(item, repair_with("Company X was founded in 2019. Product X launched in 2022."))
    assert response.repaired_verification is not None
    assert any(result.verdict is VerificationVerdict.CONTRADICTED for result in response.repaired_verification.claims)
    assert response.repair_summary.new_failed_claims == 1


def test_all_supported_claims_do_not_call_repair() -> None:
    item = request("Company X was founded in 2019.", selected("Company X was founded in 2019."))
    response = repair_and_reverify(item, lambda _: (_ for _ in ()).throw(AssertionError("should not call provider")))
    assert response.repair_summary.status is RepairStatus.NO_REPAIR_NEEDED
    assert response.repaired_draft is None


def test_no_evidence_never_calls_repair_or_invents_facts() -> None:
    item = request("Company X was founded in 2019.", [])
    response = repair_and_reverify(item, lambda _: "Invented answer")
    assert response.repaired_draft is None
    assert response.repair_summary.status is RepairStatus.STILL_FAILED


def test_provider_failure_preserves_original_verification() -> None:
    item = request("Company X was founded by Alice.", selected("Company X was founded in 2019."))
    response = repair_and_reverify(item, lambda _: (_ for _ in ()).throw(RuntimeError("provider unavailable")))
    assert response.original_verification == item.verification_report
    assert response.repaired_verification is None
    assert "provider unavailable" in response.repair_error


def test_malformed_provider_output_is_rejected_safely() -> None:
    item = request("Company X was founded by Alice.", selected("Company X was founded in 2019."))
    response = repair_and_reverify(item, lambda _: "   ")
    assert response.repaired_draft is None
    assert "empty or malformed" in response.repair_error


def test_multiple_failures_can_be_partially_repaired() -> None:
    item = request("Product X launched in 2020. Company X was founded by Alice.", selected("Product X launched in 2021. Company X was founded in 2019."))
    response = repair_and_reverify(item, repair_with("Product X launched in 2021. Company X was founded by Alice."))
    assert response.repair_summary.status is RepairStatus.PARTIALLY_FIXED
    assert response.repair_summary.still_failed_claims == 1


def test_evidence_provenance_survives_reverification() -> None:
    item = request("Product X launched in 2020.", selected("Product X launched in 2021."))
    response = repair_and_reverify(item, repair_with("Product X launched in 2021."))
    assert response.repaired_verification.claims[0].evidence[0].evidence_id == "evidence_001"


def test_supported_claim_is_preserved_in_repaired_answer() -> None:
    item = request("Company X was founded in 2019 by Alice.", selected("Company X was founded in 2019."))
    response = repair_and_reverify(item, repair_with("Company X was founded in 2019."))
    assert response.repaired_draft == "Company X was founded in 2019."
    assert response.repaired_verification.supported_count == 1


def test_protofine_style_end_to_end_repair() -> None:
    evidence = selected("Company X was founded in 2019. Alice Smith became CEO in 2021.")
    item = request("Company X was founded in 2019 by Alice Smith.", evidence)
    response = repair_and_reverify(item, repair_with("Company X was founded in 2019. Alice Smith became CEO in 2021."))
    assert [result.verdict for result in item.verification_report.claims] == [VerificationVerdict.SUPPORTED, VerificationVerdict.UNSUPPORTED]
    assert response.repaired_verification is not None
    assert response.repaired_verification.status.value == "PASSED"


def test_repair_context_keeps_ids_reasons_and_evidence_provenance() -> None:
    item = request("Company X was founded by Alice.", selected("Company X was founded in 2019."))
    context = build_repair_context(item)
    assert "Claim ID: claim_001" in context
    assert "Evidence ID: evidence_001" in context
    assert "No selected evidence establishes this claim." in context


def test_repair_loop_retries_then_only_marks_final_answer_verified_after_reverification() -> None:
    item = request("Product X launched in 2020.", selected("Product X launched in 2021."))
    answers = iter(["Product X launched in 2022.", "Product X launched in 2021."])
    response = repair_and_reverify(item, lambda _: next(answers))
    assert response.repair_summary.iterations == 2
    assert response.repaired_verification is not None
    assert response.repaired_verification.status.value == "PASSED"
    assert response.repair_summary.status is RepairStatus.FIXED


def test_repair_loop_stops_at_the_bounded_attempt_limit() -> None:
    item = request("Product X launched in 2020.", selected("Product X launched in 2021."))
    response = repair_and_reverify(item, lambda _: "Product X launched in 2022.")
    assert response.repair_summary.iterations == 2
    assert response.repaired_verification is not None
    assert response.repaired_verification.status.value == "FAILED"
    assert response.repair_summary.status is not RepairStatus.FIXED
