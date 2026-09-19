"""Deterministic, evidence-bounded evaluation of atomic factual claims."""

import re

from pydantic import BaseModel, Field, ValidationError

from core.models import Claim, ClaimVerification, EvidenceItem, EvidenceReference, VerificationReport, VerificationStatus, VerificationVerdict

STOP_WORDS = frozenset({"a", "an", "and", "are", "as", "at", "by", "for", "from", "in", "is", "it", "of", "on", "the", "to", "was", "were", "with"})


class VerificationError(ValueError):
    """A verification request or future provider decision is invalid."""


class VerifierDecision(BaseModel):
    """Strict future-provider schema, validated before acceptance."""

    claim_id: str
    verdict: VerificationVerdict
    evidence: list[EvidenceReference] = Field(default_factory=list)
    reason: str = Field(min_length=1)


def verify_claim(claim: Claim, evidence: list[EvidenceItem]) -> ClaimVerification:
    """Evaluate one claim using only supplied evidence and exact excerpts."""
    segments = _relevant_segments(claim, evidence)
    for item, excerpt in segments:
        if _supports(claim.text, excerpt):
            return _result(claim, VerificationVerdict.SUPPORTED, [_reference(item, excerpt)], "The selected evidence explicitly establishes this claim.")
    for item, excerpt in segments:
        conflict = _contradiction(claim.text, excerpt)
        if conflict:
            return _result(claim, VerificationVerdict.CONTRADICTED, [_reference(item, excerpt)], conflict)
    references = [_reference(item, excerpt) for item, excerpt in segments[:2]]
    reason = "No selected evidence establishes this claim." if evidence else "No selected evidence was provided for verification."
    return _result(claim, VerificationVerdict.UNSUPPORTED, references, reason)


def verify_claims(claims: list[Claim], evidence: list[EvidenceItem]) -> VerificationReport:
    """Return an independent, auditable result for every supplied claim."""
    _validate_inputs(claims, evidence)
    results = [verify_claim(claim, evidence) for claim in claims]
    supported = sum(result.verdict is VerificationVerdict.SUPPORTED for result in results)
    unsupported = sum(result.verdict is VerificationVerdict.UNSUPPORTED for result in results)
    contradicted = sum(result.verdict is VerificationVerdict.CONTRADICTED for result in results)
    status = VerificationStatus.PASSED if not unsupported and not contradicted else VerificationStatus.FAILED
    summary = "No unsupported claims detected against the selected evidence." if status is VerificationStatus.PASSED else f"Reliability issues detected: {unsupported + contradicted} claim(s) require attention."
    return VerificationReport(status=status, total_claims=len(results), supported_count=supported, unsupported_count=unsupported, contradicted_count=contradicted, claims=results, summary=summary)


def validate_verifier_decision(payload: object, claim: Claim, evidence: list[EvidenceItem]) -> ClaimVerification:
    """Validate future LLM output against this exact claim and evidence context."""
    try:
        decision = VerifierDecision.model_validate(payload)
    except ValidationError as error:
        raise VerificationError("Verifier returned malformed structured output.") from error
    if decision.claim_id != claim.id:
        raise VerificationError("Verifier returned a decision for an unknown claim ID.")
    evidence_by_id = {item.id: item for item in evidence}
    for reference in decision.evidence:
        item = evidence_by_id.get(reference.evidence_id)
        if item is None:
            raise VerificationError("Verifier referenced an evidence ID outside the selected context.")
        if reference.source_name != item.source_name or reference.page_number != item.page_number:
            raise VerificationError("Verifier altered evidence provenance metadata.")
        if reference.relevant_excerpt not in item.content:
            raise VerificationError("Verifier returned an excerpt not found in selected evidence.")
    return _result(claim, decision.verdict, decision.evidence, decision.reason)


def _validate_inputs(claims: list[Claim], evidence: list[EvidenceItem]) -> None:
    if len({claim.id for claim in claims}) != len(claims):
        raise VerificationError("Verification requires unique claim IDs.")
    if len({item.id for item in evidence}) != len(evidence):
        raise VerificationError("Verification requires unique evidence IDs.")


def _relevant_segments(claim: Claim, evidence: list[EvidenceItem]) -> list[tuple[EvidenceItem, str]]:
    claim_tokens = _tokens(claim.text)
    segments: list[tuple[int, EvidenceItem, str]] = []
    for item in evidence:
        for excerpt in _sentences(item.content):
            overlap = len(claim_tokens & _tokens(excerpt))
            if overlap:
                segments.append((overlap, item, excerpt))
    return [(item, excerpt) for _, item, excerpt in sorted(segments, key=lambda entry: entry[0], reverse=True)]


def _supports(claim: str, excerpt: str) -> bool:
    claim_norm, excerpt_norm = _normal(claim), _normal(excerpt)
    if claim_norm in excerpt_norm:
        return True
    claim_fact, evidence_fact = _fact(claim), _fact(excerpt)
    if claim_fact and evidence_fact and claim_fact == evidence_fact:
        return True
    identity = _ceo_identity(claim)
    return bool(identity and identity[0] in _normal(excerpt) and "ceo" in _normal(excerpt) and identity[1] in _normal(excerpt))


def _contradiction(claim: str, excerpt: str) -> str | None:
    claim_identity, evidence_identity = _ceo_identity(claim), _ceo_identity(excerpt)
    if claim_identity and evidence_identity and claim_identity[1] == evidence_identity[1] and claim_identity[0] != evidence_identity[0]:
        return f"Selected evidence states '{excerpt}', which identifies a different CEO."
    claim_fact, evidence_fact = _fact(claim), _fact(excerpt)
    if claim_fact and evidence_fact and claim_fact[0] == evidence_fact[0] and claim_fact[1] == evidence_fact[1] and claim_fact[2] != evidence_fact[2]:
        if _tokens(evidence_fact[2]) <= _tokens(claim_fact[2]):
            return None
        return f"Selected evidence states '{excerpt}', which conflicts with the claim."
    if claim_fact and evidence_fact and claim_fact[1] == evidence_fact[1] and claim_fact[2] == evidence_fact[2] and claim_fact[0] != evidence_fact[0]:
        return f"Selected evidence states '{excerpt}', which identifies a different entity than the claim."
    claim_year, evidence_year = _year(claim), _year(excerpt)
    if claim_year and evidence_year and claim_year != evidence_year and _same_relation(claim, excerpt):
        return f"Selected evidence states '{excerpt}', which conflicts with the claim's date or year."
    claim_percent, calculated_percent = _percent(claim), _calculated_percent(excerpt)
    if claim_percent is not None and calculated_percent is not None and abs(claim_percent - calculated_percent) > 0.01:
        return f"Selected evidence states '{excerpt}', which yields {calculated_percent:g}% rather than {claim_percent:g}%."
    return None


def _ceo_identity(text: str) -> tuple[str, str] | None:
    """Recognize the two common word orders for a CEO identity statement."""
    normalized = _normal(text)
    role_first = re.match(r"^the ceo of (.+?) is (.+)$", normalized)
    if role_first:
        return (role_first.group(2), role_first.group(1))
    person_first = re.match(r"^(.+?) is (?:the )?ceo of (.+)$", normalized)
    if person_first:
        return (person_first.group(1), person_first.group(2))
    return None


def _fact(text: str) -> tuple[str, str, str] | None:
    normalized = _normal(text)
    patterns = (r"^(.+?) was (founded|established) (in|by) (.+)$", r"^(.+?) (launched|released) (?:in )?(.+)$", r"^(.+?) is headquartered in (.+)$", r"^(.+?) acquired (.+)$")
    for pattern in patterns:
        match = re.match(pattern, normalized)
        if match:
            parts = match.groups()
            if len(parts) == 4:
                return (parts[0], f"founded_{parts[2]}", parts[3])
            if len(parts) == 2:
                return (parts[0], "acquired", parts[1])
            return (parts[0], parts[1], parts[2])
    return None


def _same_relation(first: str, second: str) -> bool:
    first_fact, second_fact = _fact(first), _fact(second)
    if first_fact and second_fact:
        return first_fact[0] == second_fact[0] and first_fact[1] == second_fact[1]
    return len(_tokens(first) & _tokens(second)) >= 2


def _normal(text: str) -> str:
    normalized = text.lower().replace("established", "founded")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9% ]", " ", normalized)).strip()


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9%]+", text.lower()) if token not in STOP_WORDS}


def _sentences(content: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", content) if part.strip()]
    # HTML extraction often puts a heading/name in one block and its descriptive
    # sentence in the next. Adjacent combinations remain verbatim source excerpts.
    return parts + [f"{parts[index]}\n{parts[index + 1]}" for index in range(len(parts) - 1)]


def _year(text: str) -> str | None:
    match = re.search(r"\b(?:19|20)\d{2}\b", text)
    return match.group(0) if match else None


def _percent(text: str) -> float | None:
    match = re.search(r"\b(\d+(?:\.\d+)?)%", text)
    return float(match.group(1)) if match else None


def _calculated_percent(text: str) -> float | None:
    match = re.search(r"increased from\s*(?:[^\d]*)(\d+(?:\.\d+)?)\s*(?:million|m)?\s+to\s*(?:[^\d]*)(\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if not match:
        return None
    initial, final = map(float, match.groups())
    return ((final - initial) / initial) * 100 if initial else None


def _reference(item: EvidenceItem, excerpt: str) -> EvidenceReference:
    return EvidenceReference(evidence_id=item.id, source_name=item.source_name, page_number=item.page_number, relevant_excerpt=excerpt)


def _result(claim: Claim, verdict: VerificationVerdict, evidence: list[EvidenceReference], reason: str) -> ClaimVerification:
    return ClaimVerification(claim_id=claim.id, claim=claim, verdict=verdict, evidence=evidence, reason=reason)
