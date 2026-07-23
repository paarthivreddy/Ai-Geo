"""Audit trail value objects for GeoCare AI."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID


class ProcessingMethod(str, Enum):
    """Processing method types for audit entries."""

    NORMALIZATION = "normalization"
    PARSING = "parsing"
    PIN_RESOLUTION = "pin_resolution"
    LOCALITY_MATCH = "locality_match"
    SPELL_CORRECTION = "spell_correction"
    HIERARCHY_ENRICHMENT = "hierarchy_enrichment"
    VALIDATION_CORRECTION = "validation_correction"
    MANUAL_OVERRIDE = "manual_override"


class DataSource(str, Enum):
    """Data source types for audit entries."""

    INDIA_POST = "india_post"
    OSM = "osm"
    CENSUS = "census"
    LIBPOSTAL = "libpostal"
    RAPIDFUZZ = "rapidfuzz"
    MANUAL = "manual"
    INFERRED = "inferred"


@dataclass
class AuditEntry:
    """Immutable audit entry for a single field transformation."""

    id: UUID
    record_id: UUID
    job_id: UUID
    field_name: str
    old_value: Optional[str]
    new_value: Optional[str]
    processing_method: ProcessingMethod
    confidence: int  # 0-100
    source_dataset: DataSource
    user_id: Optional[UUID] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 100:
            raise ValueError("Confidence must be between 0 and 100")


@dataclass
class AuditSummary:
    """Aggregated audit statistics for a job."""

    total_changes: int = 0
    by_method: dict[str, int] = field(default_factory=dict)
    by_field: dict[str, int] = field(default_factory=dict)
    avg_confidence: float = 0.0
    user_overrides: int = 0

    @classmethod
    def from_entries(cls, entries: list[AuditEntry]) -> "AuditSummary":
        from collections import Counter

        if not entries:
            return cls()

        by_method = Counter(e.processing_method.value for e in entries)
        by_field = Counter(e.field_name for e in entries)
        avg_conf = sum(e.confidence for e in entries) / len(entries)
        user_overrides = sum(1 for e in entries if e.user_id is not None)

        return cls(
            total_changes=len(entries),
            by_method=dict(by_method),
            by_field=dict(by_field),
            avg_confidence=round(avg_conf, 2),
            user_overrides=user_overrides,
        )