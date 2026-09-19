"""Small process-local evidence collection for the current development stage."""

from threading import RLock

from core.models import EvidenceItem


class EvidenceStore:
    """Thread-safe in-memory storage, replaceable by a future session layer."""

    def __init__(self) -> None:
        self._items: dict[str, EvidenceItem] = {}
        self._lock = RLock()

    def add_many(self, items: list[EvidenceItem]) -> list[EvidenceItem]:
        with self._lock:
            self._items.update({item.id: item for item in items})
        return items

    def list_all(self) -> list[EvidenceItem]:
        with self._lock:
            return list(self._items.values())

    def remove(self, evidence_id: str) -> bool:
        with self._lock:
            return self._items.pop(evidence_id, None) is not None
