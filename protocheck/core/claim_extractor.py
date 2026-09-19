"""Conservative, deterministic extraction of complete factual assertions."""

import re

from core.models import Claim, ClaimImportance, ClaimType


class ClaimExtractionError(ValueError):
    """The supplied draft cannot be safely processed into structured claims."""


_VERBS = r"is|are|was|were|has|have|had|founded|established|launched|released|produces|supports|includes|contains|increased|decreased|allows|requires|became|acquired|headquartered|located|created|published|announced|joined|serving"
_META = re.compile(r"^(?:here (?:are|is)|for example|if you mean|note:|clarification:|summary:|important:|the answer is|you can|please |let's )", re.I)


def extract_claims(answer: str) -> list[Claim]:
    """Extract facts from this draft only; never verify or correct them."""
    if not answer or not answer.strip():
        raise ClaimExtractionError("Draft answer is empty.")
    candidates: list[tuple[str, str]] = []
    antecedent = ""
    for sentence in _sentences(answer):
        resolved = _resolve_pronoun(sentence, antecedent)
        candidates.extend((claim, sentence) for claim, _ in _extract(resolved))
        antecedent = _next_antecedent(resolved, antecedent)
    unique = _deduplicate(candidates)
    return [Claim(id=f"claim_{i:03d}", text=text, claim_type=_classify(text),
                  source_sentence=source, importance=_importance(text))
            for i, (text, source) in enumerate(unique, 1)]


def _sentences(answer: str) -> list[str]:
    lines: list[str] = []
    for raw in answer.splitlines():
        line = re.sub(r"^\s{0,3}(?:#{1,6}\s+|[-*+]\s+|\d+[.)]\s+|>\s*)", "", raw).strip()
        line = re.sub(r"[*_`]+", "", line).strip()
        if line and not _is_heading(line):
            lines.append(line)
    return [part.strip() for line in lines for part in re.split(r"(?<=[.!?])\s+", line) if part.strip()]


def _is_heading(text: str) -> bool:
    return (len(text.split()) <= 8 and not re.search(r"\b(?:" + _VERBS + r")\b|\d", text, re.I)
            and (text.isupper() or text.endswith(":")))


def _extract(sentence: str) -> list[tuple[str, str]]:
    if not _acceptable(sentence):
        return []
    founder = re.fullmatch(r"(.+?)\s+was\s+(founded|established)\s+(on|in)\s+(.+?)\s+by\s+(.+?)([.!])?", sentence, re.I)
    if founder:
        subject, verb, preposition, date, people, punctuation = founder.groups()
        end = punctuation or "."
        claims = [(f"{subject} was {verb} {preposition} {date}{end}", sentence)]
        for person in re.split(r"\s*,\s*|\s+and\s+", people):
            person = re.sub(r"^and\s+", "", person.strip(), flags=re.I)
            if person:
                claims.append((f"{person} was one of {subject}'s founders{end}", sentence))
        return claims
    return [(claim, sentence) for claim in _split_compound(sentence) if _acceptable(claim)]


def _resolve_pronoun(sentence: str, antecedent: str) -> str:
    """Make a directly adjacent he/she/they claim independently readable."""
    if antecedent and re.match(r"^(?:he|she|they)\b", sentence, re.I):
        return re.sub(r"^(?:he|she|they)\b", antecedent, sentence, count=1, flags=re.I)
    return sentence


def _next_antecedent(sentence: str, current: str) -> str:
    # Handles concise identity statements such as "The CEO of Google is Sundar Pichai."
    identity = re.search(r"\b(?:is|was)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)[.!]?$", sentence)
    if identity:
        return identity.group(1)
    subject = re.match(r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s+\b(?:" + _VERBS + r")\b", sentence)
    return subject.group(1) if subject else current


def _split_compound(sentence: str) -> list[str]:
    end = "." if sentence[-1:] not in ".!" else sentence[-1]
    body = sentence.rstrip(".!")
    timeline = re.fullmatch(r"(.+?)\s+has been serving as\s+(.+?)\s+since\s+(.+?),\s+and\s+in\s+(.+?),\s+(?:he|she|they|\1)\s+(?:also\s+)?became\s+(.+)", body, re.I)
    if timeline:
        subject, role, first_date, second_date, second_role = timeline.groups()
        return [f"{subject} has been serving as {role} since {first_date}{end}", f"{subject} became {second_role} in {second_date}{end}"]
    possessive = re.fullmatch(r"(.+?)\s+was\s+(.+?)\s+and\s+its\s+(.+?)\s+(is|are|was|were)\s+(.+)", body, re.I)
    if possessive:
        subject, first_value, noun, verb, second_value = possessive.groups()
        return [f"{subject} was {first_value}{end}", f"{subject}'s {noun} {verb} {second_value}{end}"]
    match = re.match(r"^(.+?)\s+((?:" + _VERBS + r")\b.+)$", body, re.I)
    if not match:
        return [sentence]
    subject, predicates = match.groups()
    parts = re.split(r",\s*(?:and\s+)?(?=(?:" + _VERBS + r")\b)|\s+and\s+(?=(?:" + _VERBS + r")\b)", predicates, flags=re.I)
    claims: list[str] = []
    for part in parts:
        claim = f"{subject} {part.strip()}{end}"
        platform_match = re.fullmatch(r"(.+?)\s+(is available on|supports)\s+(.+?)\s+and\s+(.+?)[.!]", claim, re.I)
        if platform_match:
            platform_subject, verb, first, second = platform_match.groups()
            claims.extend([f"{platform_subject} {verb} {first}{end}", f"{platform_subject} {verb} {second}{end}"])
        elif part.strip():
            claims.append(claim)
    return claims


def _acceptable(text: str) -> bool:
    clean = text.strip()
    lower = clean.lower()
    if not clean or clean.endswith("?") or _META.match(clean):
        return False
    if re.match(r"^(?:because|although|while|if|when|since)\b", lower):
        return False
    if re.match(r"^(?:hello|hi|thanks|thank you|sure|yes|no)[!. ,]*$", lower):
        return False
    return bool(re.search(r"\b(?:" + _VERBS + r")\b", clean, re.I)) and len(clean.split()) >= 3


def _deduplicate(candidates: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[str] = set()
    output: list[tuple[str, str]] = []
    for text, source in candidates:
        canonical = text.lower().replace("established", "founded")
        canonical = re.sub(r"^the company\b", "company x", canonical)
        key = re.sub(r"[^a-z0-9]+", " ", canonical).strip()
        if key not in seen:
            seen.add(key)
            output.append((text, source))
    return output


def _classify(text: str) -> ClaimType:
    lower = text.lower()
    if re.search(r"\b(?:because|caused|resulted in|by reducing|by increasing)\b", lower): return ClaimType.CAUSAL
    if re.search(r"\b(?:more|less|higher|lower|than)\b", lower): return ClaimType.COMPARATIVE
    if re.search(r"\b(19|20)\d{2}\b|\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b", lower): return ClaimType.TEMPORAL
    if re.search(r"\b\d+(?:\.\d+)?%?\b", text): return ClaimType.NUMERICAL
    return ClaimType.FACTUAL


def _importance(text: str) -> ClaimImportance:
    return ClaimImportance.HIGH if re.search(r"\b\d|\b(?:must|required|only)\b", text, re.I) else ClaimImportance.NORMAL
