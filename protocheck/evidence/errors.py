"""User-safe errors raised by deterministic evidence ingestion."""


class EvidenceLoadError(ValueError):
    """Evidence cannot be safely accepted or read."""


class UnsupportedEvidenceTypeError(EvidenceLoadError):
    """A source does not use one of the supported evidence formats."""
