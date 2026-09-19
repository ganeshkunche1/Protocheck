"""Shared structured models for ProtoCheck."""

from enum import Enum

from pydantic import BaseModel, Field


class VerificationVerdict(str, Enum):
    """Possible relationships between a claim and selected evidence."""

    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    CONTRADICTED = "CONTRADICTED"


class VerificationStatus(str, Enum):
    """Summary state derived from claim-level verdicts."""

    PASSED = "PASSED"
    FAILED = "FAILED"


class RepairStatus(str, Enum):
    """Evidence-grounded outcome of a repair attempt."""

    NO_REPAIR_NEEDED = "NO_REPAIR_NEEDED"
    FIXED = "FIXED"
    PARTIALLY_FIXED = "PARTIALLY_FIXED"
    STILL_FAILED = "STILL_FAILED"


class RepairClaimOutcomeType(str, Enum):
    """What happened to an original failed claim after re-verification."""

    FIXED = "FIXED"
    REMOVED = "REMOVED"
    QUALIFIED = "QUALIFIED"
    STILL_FAILED = "STILL_FAILED"


class EvidenceSourceType(str, Enum):
    """User-provided evidence formats supported by the application."""

    PASTED_TEXT = "PASTED_TEXT"
    TXT = "TXT"
    PDF = "PDF"
    WEB = "WEB"


class ClaimType(str, Enum):
    """Lightweight categories that help a future verifier prioritize checks."""

    FACTUAL = "FACTUAL"
    NUMERICAL = "NUMERICAL"
    TEMPORAL = "TEMPORAL"
    CAUSAL = "CAUSAL"
    COMPARATIVE = "COMPARATIVE"
    PROCEDURAL = "PROCEDURAL"


class ClaimImportance(str, Enum):
    """A deliberately small importance scale for future report presentation."""

    NORMAL = "NORMAL"
    HIGH = "HIGH"


class PromptRequest(BaseModel):
    prompt: str = Field(min_length=1)


class DraftResponse(BaseModel):
    answer: str


class SourceRecommendation(BaseModel):
    """A discoverable source, not evidence until its content is imported."""

    id: str
    title: str
    url: str
    domain: str
    description: str = ""
    source_type: str = "WEB"
    relevance_reason: str = ""
    is_official: bool = False
    selected: bool = False
    retrieval_status: str = "NOT_RETRIEVED"


class SourceRecommendationResponse(BaseModel):
    recommendations: list[SourceRecommendation] = Field(default_factory=list)
    available: bool = True
    status: str = "available"
    message: str | None = None


class Claim(BaseModel):
    """One independently verifiable statement found in a draft answer."""

    id: str
    text: str
    claim_type: ClaimType = ClaimType.FACTUAL
    source_sentence: str
    importance: ClaimImportance = ClaimImportance.NORMAL


class ClaimExtractionRequest(BaseModel):
    """Draft answer supplied for non-verifying claim extraction."""

    draft_answer: str = Field(min_length=1)


class ClaimExtractionResponse(BaseModel):
    """Structured claims extracted from a single draft answer."""

    claims: list[Claim] = Field(default_factory=list)


class VerificationContext(BaseModel):
    """Current-analysis selection boundary for a future verification stage.

    Selected IDs are references only; they do not imply that recommended
    sources have been retrieved or that any evidence has been verified.
    """

    prompt: str
    draft_answer: str
    selected_evidence_ids: list[str] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    """Normalized, provenance-preserving evidence for future verification."""

    id: str
    source_name: str
    source_type: EvidenceSourceType
    content: str
    file_name: str | None = None
    page_number: int | None = Field(default=None, ge=1)
    mime_type: str | None = None
    url: str | None = None
    domain: str | None = None
    title: str | None = None
    retrieval_status: str | None = None
    character_count: int = Field(ge=0)


class PastedEvidenceRequest(BaseModel):
    content: str
    source_name: str | None = None


class WebEvidenceRequest(BaseModel):
    """One explicitly selected recommendation to retrieve as evidence."""

    url: str
    source_name: str | None = None


class EvidenceCollectionResponse(BaseModel):
    """Current process-local evidence collection."""

    items: list[EvidenceItem] = Field(default_factory=list)


class EvidenceReference(BaseModel):
    """Auditable excerpt from an item in the selected evidence context."""

    evidence_id: str
    source_name: str
    page_number: int | None = Field(default=None, ge=1)
    relevant_excerpt: str = Field(min_length=1)


class ClaimVerification(BaseModel):
    """Evidence-bounded decision for one extracted claim."""

    claim_id: str
    claim: Claim
    verdict: VerificationVerdict
    evidence: list[EvidenceReference] = Field(default_factory=list)
    reason: str


class VerificationReport(BaseModel):
    status: VerificationStatus
    total_claims: int = Field(ge=0)
    supported_count: int = Field(ge=0)
    unsupported_count: int = Field(ge=0)
    contradicted_count: int = Field(ge=0)
    claims: list[ClaimVerification] = Field(default_factory=list)
    summary: str


class VerificationRequest(BaseModel):
    """Selected evidence and extracted claims to evaluate in the current session."""

    claims: list[Claim] = Field(default_factory=list)
    selected_evidence: list[EvidenceItem] = Field(default_factory=list)


class RepairRequest(BaseModel):
    """Everything needed to produce an evidence-constrained repair."""

    original_prompt: str = ""
    original_draft: str = Field(min_length=1)
    claims: list[Claim]
    verification_report: VerificationReport
    selected_evidence: list[EvidenceItem]


class RepairClaimOutcome(BaseModel):
    """Re-verification outcome for one originally failed claim."""

    original_claim_id: str
    outcome: RepairClaimOutcomeType
    detail: str


class RepairSummary(BaseModel):
    """Compact, evidence-based comparison of original and repaired results."""

    status: RepairStatus
    fixed_claims: int = Field(ge=0)
    removed_claims: int = Field(ge=0)
    qualified_claims: int = Field(ge=0)
    still_failed_claims: int = Field(ge=0)
    new_failed_claims: int = Field(ge=0)
    iterations: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=2, ge=1)
    outcomes: list[RepairClaimOutcome] = Field(default_factory=list)


class FinalResponse(BaseModel):
    """Before/after result; repaired output is never trusted without re-checking."""

    original_draft: str
    repaired_draft: str | None = None
    original_verification: VerificationReport
    repaired_verification: VerificationReport | None = None
    repair_summary: RepairSummary
    repair_error: str | None = None
