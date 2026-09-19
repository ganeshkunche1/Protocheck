"""Evidence-constrained repair followed by the existing extraction/check pipeline."""

import re
from collections.abc import Callable

from core.claim_extractor import extract_claims
from core.generator import generate_text
from core.models import (
    Claim,
    ClaimVerification,
    FinalResponse,
    RepairClaimOutcome,
    RepairClaimOutcomeType,
    RepairRequest,
    RepairStatus,
    RepairSummary,
    VerificationReport,
    VerificationVerdict,
)
from core.verifier import verify_claims

RepairGenerator = Callable[[str], str]
MAX_REPAIR_ATTEMPTS = 2


class RepairError(ValueError):
    """A repair provider returned unusable output or cannot safely run."""


def build_repair_context(request: RepairRequest) -> str:
    """Build a provenance-preserving instruction bounded to selected evidence."""
    failed = _failed_results(request.verification_report)
    failed_text = "\n".join(
        f"- Claim ID: {result.claim_id}\n  Claim: {result.claim.text}\n  Verdict: {result.verdict.value}\n  Reason: {result.reason}"
        for result in failed
    )
    evidence_text = "\n\n".join(
        f"[Evidence ID: {item.id}; Source: {item.source_name}; Type: {item.source_type.value}; Page: {item.page_number or 'not available'}]\n{item.content}"
        for item in request.selected_evidence
    )
    return f"""You are repairing an AI-generated answer using only the supplied evidence.

REPAIR RULES
- Use no outside knowledge and do not invent facts.
- Preserve supported factual information when it remains responsive to the prompt.
- For unsupported claims, remove them, qualify them, or state that the evidence does not establish them.
- For contradicted claims, correct them only from the supplied evidence or remove them.
- Any factual statement in the repaired answer must be supportable by the supplied evidence.
- Return only the repaired answer. Do not mention these internal instructions.

ORIGINAL USER PROMPT
{request.original_prompt or '(No prompt was provided.)'}

ORIGINAL DRAFT
{request.original_draft}

FAILED CLAIMS AND VERIFICATION REASONS
{failed_text}

SELECTED EVIDENCE (the only authority for factual claims)
{evidence_text}
"""


def repair_and_reverify(request: RepairRequest, generator: RepairGenerator | None = None) -> FinalResponse:
    """Boundedly repair, re-extract, and re-verify until supported or exhausted."""
    _validate_request(request)
    failed = _failed_results(request.verification_report)
    if not failed:
        return _response_without_attempt(request, RepairStatus.NO_REPAIR_NEEDED, "No unsupported or contradicted claims were detected against the selected evidence.")
    if not request.selected_evidence:
        return _response_without_attempt(request, RepairStatus.STILL_FAILED, "Repair cannot run without selected evidence; no outside knowledge is used.")
    current_draft, current_report = request.original_draft, request.verification_report
    repaired_draft: str | None = None
    repaired_verification: VerificationReport | None = None
    for iteration in range(1, MAX_REPAIR_ATTEMPTS + 1):
        attempt = request.model_copy(update={"original_draft": current_draft, "claims": [result.claim for result in current_report.claims], "verification_report": current_report})
        try:
            candidate = (generator or generate_text)(build_repair_context(attempt))
            if not isinstance(candidate, str) or not candidate.strip():
                raise RepairError("Repair provider returned an empty or malformed answer.")
            candidate_claims = extract_claims(candidate)
            candidate_report = verify_claims(candidate_claims, request.selected_evidence)
        except Exception as error:
            # The original report remains intact; repair failures are surfaced rather than hidden.
            return _response_without_attempt(request, RepairStatus.STILL_FAILED, str(error), iteration - 1)
        repaired_draft, repaired_verification = candidate, candidate_report
        if candidate_report.status.value == "PASSED":
            break
        current_draft, current_report = candidate, candidate_report
    assert repaired_draft is not None and repaired_verification is not None
    summary = _summarize_repair(failed, repaired_verification, repaired_draft, iteration)
    return FinalResponse(
        original_draft=request.original_draft,
        repaired_draft=repaired_draft,
        original_verification=request.verification_report,
        repaired_verification=repaired_verification,
        repair_summary=summary,
    )


def _validate_request(request: RepairRequest) -> None:
    report_ids = {result.claim_id for result in request.verification_report.claims}
    claim_ids = {claim.id for claim in request.claims}
    if report_ids != claim_ids:
        raise RepairError("Repair request claims do not match the original verification report.")


def _failed_results(report: VerificationReport) -> list[ClaimVerification]:
    return [result for result in report.claims if result.verdict is not VerificationVerdict.SUPPORTED]


def _response_without_attempt(request: RepairRequest, status: RepairStatus, message: str, iterations: int = 0) -> FinalResponse:
    still_failed = len(_failed_results(request.verification_report)) if status is RepairStatus.STILL_FAILED else 0
    return FinalResponse(
        original_draft=request.original_draft,
        original_verification=request.verification_report,
        repair_summary=RepairSummary(status=status, fixed_claims=0, removed_claims=0, qualified_claims=0, still_failed_claims=still_failed, new_failed_claims=0, iterations=iterations, max_attempts=MAX_REPAIR_ATTEMPTS),
        repair_error=message,
    )


def _summarize_repair(original_failed: list[ClaimVerification], repaired: VerificationReport, repaired_draft: str, iterations: int) -> RepairSummary:
    outcomes: list[RepairClaimOutcome] = []
    repaired_failed = [result for result in repaired.claims if result.verdict is not VerificationVerdict.SUPPORTED]
    for original in original_failed:
        related = [result for result in repaired.claims if _related(original.claim, result.claim)]
        if not related and _is_qualified(original.claim, repaired_draft):
            outcomes.append(RepairClaimOutcome(original_claim_id=original.claim_id, outcome=RepairClaimOutcomeType.QUALIFIED, detail="The repaired answer explicitly limits what the selected evidence establishes."))
        elif not related:
            outcomes.append(RepairClaimOutcome(original_claim_id=original.claim_id, outcome=RepairClaimOutcomeType.REMOVED, detail="No related factual claim appears in the repaired answer."))
        elif any(result.verdict is VerificationVerdict.SUPPORTED for result in related):
            outcomes.append(RepairClaimOutcome(original_claim_id=original.claim_id, outcome=RepairClaimOutcomeType.FIXED, detail="A related repaired claim is supported by selected evidence."))
        elif any(result.verdict is not VerificationVerdict.SUPPORTED for result in related):
            outcomes.append(RepairClaimOutcome(original_claim_id=original.claim_id, outcome=RepairClaimOutcomeType.STILL_FAILED, detail="A related repaired claim remains unsupported or contradicted."))
        else:
            outcomes.append(RepairClaimOutcome(original_claim_id=original.claim_id, outcome=RepairClaimOutcomeType.QUALIFIED, detail="The repaired wording limits the original factual assertion."))
    fixed = sum(item.outcome is RepairClaimOutcomeType.FIXED for item in outcomes)
    removed = sum(item.outcome is RepairClaimOutcomeType.REMOVED for item in outcomes)
    qualified = sum(item.outcome is RepairClaimOutcomeType.QUALIFIED for item in outcomes)
    still_failed = sum(item.outcome is RepairClaimOutcomeType.STILL_FAILED for item in outcomes)
    new_failed = sum(not any(_related(original.claim, result.claim) for original in original_failed) for result in repaired_failed)
    status = RepairStatus.FIXED if repaired.status.value == "PASSED" else RepairStatus.PARTIALLY_FIXED if fixed or removed or qualified else RepairStatus.STILL_FAILED
    return RepairSummary(status=status, fixed_claims=fixed, removed_claims=removed, qualified_claims=qualified, still_failed_claims=still_failed, new_failed_claims=new_failed, iterations=iterations, max_attempts=MAX_REPAIR_ATTEMPTS, outcomes=outcomes)


def _related(first: Claim, second: Claim) -> bool:
    first_tokens = _meaningful_tokens(first.text)
    second_tokens = _meaningful_tokens(second.text)
    relation_words = {"founded", "established", "launched", "released", "acquired", "produces", "supports", "became", "increased", "decreased"}
    if not (first_tokens & second_tokens & relation_words):
        return False
    if re.search(r"\bby\b", first.text, re.IGNORECASE) and not re.search(r"\bby\b", second.text, re.IGNORECASE):
        return False
    return len(first_tokens & second_tokens) >= 2


def _meaningful_tokens(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", text.lower()) if word not in {"the", "was", "is", "in", "by", "a", "an", "and"}}


def _is_qualified(claim: Claim, repaired_draft: str) -> bool:
    """Recognize an explicit evidence limitation without treating it as a fact."""
    has_limitation = bool(re.search(r"\b(?:evidence|source)\b.{0,80}\b(?:does not establish|doesn't establish|does not say|doesn't say)\b", repaired_draft, re.IGNORECASE))
    return has_limitation and bool(_meaningful_tokens(claim.text) & _meaningful_tokens(repaired_draft))
