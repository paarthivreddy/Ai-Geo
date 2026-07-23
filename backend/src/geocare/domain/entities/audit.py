"""Audit entry entity for GeoCare AI."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4


class ProcessingMethod(str, Enum):
    NORMALIZATION = "normalization"
    PARSING = "parsing"
    PIN_RESOLUTION = "pin_resolution"
    LOCALITY_MATCH = "locality_match"
    SPELL_CORRECTION = "spell_correction"
    HIERARCHY_ENRICHMENT = "hierarchy_enrichment"
    VALIDATION_CORRECTION = "validation_correction"
    MANUAL_OVERRIDE = "manual_override"


class DataSource(str, Enum):
    INDIA_POST = "india_post"
    OSM = "osm"
    CENSUS = "census"
    LIBPOSTAL = "libpostal"
    RAPIDFUZZ = "rapidfuzz"
    MANUAL = "manual"
    INFERRED = "inferred"


@dataclass
class AuditEntry:
    """Immutable audit trail entry for address transformation."""

    id: UUID = field(default_factory=uuid4)
    record_id: UUID = field(default_factory=uuid4)
    job_id: UUID = field(default_factory=uuid4)
    field_name: str = ""
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    processing_method: ProcessingMethod = ProcessingMethod.MANUAL_OVERRIDE
    confidence: int = 0
    source_dataset: DataSource = DataSource.MANUAL
    user_id: Optional[UUID] = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 100:
            raise ValueError("Confidence must be between 0 and 100")