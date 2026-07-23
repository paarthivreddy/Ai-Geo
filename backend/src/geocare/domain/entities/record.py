"""Record entity for GeoCare AI."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID, uuid4


class ReviewStatus(str, Enum):
    AUTO = "auto"
    NEEDS_REVIEW = "needs_review"
    MANUAL_VERIFIED = "manual_verified"
    REJECTED = "rejected"


class ConfidenceTier(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNVERIFIED = "unverified"


class MatchMethod(str, Enum):
    EXACT = "exact"
    FUZZY = "fuzzy"
    INFERRED = "inferred"
    MANUAL = "manual"


@dataclass
class ConfidenceScore:
    """Confidence score breakdown."""

    overall: int = 0
    pincode_validity: int = 0
    locality_match: int = 0
    hierarchy_consistency: int = 0
    parsing_completeness: int = 0
    fuzzy_quality: int = 0
    method: MatchMethod = MatchMethod.MANUAL
    tier: ConfidenceTier = ConfidenceTier.UNVERIFIED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall": self.overall,
            "pincode_validity": self.pincode_validity,
            "locality_match": self.locality_match,
            "hierarchy_consistency": self.hierarchy_consistency,
            "parsing_completeness": self.parsing_completeness,
            "fuzzy_quality": self.fuzzy_quality,
            "method": self.method.value,
            "tier": self.tier.value,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConfidenceScore":
        return cls(
            overall=data.get("overall", 0),
            pincode_validity=data.get("pincode_validity", 0),
            locality_match=data.get("locality_match", 0),
            hierarchy_consistency=data.get("hierarchy_consistency", 0),
            parsing_completeness=data.get("parsing_completeness", 0),
            fuzzy_quality=data.get("fuzzy_quality", 0),
            method=MatchMethod(data.get("method", "manual")),
            tier=ConfidenceTier(data.get("tier", "unverified")),
        )


@dataclass
class PatientRecord:
    """Patient record entity."""

    id: UUID = field(default_factory=uuid4)
    job_id: UUID = field(default_factory=uuid4)
    row_index: int = 0
    patient_id_hash: str = ""

    # Address stages
    original_address: Dict[str, Any] = field(default_factory=dict)
    normalized_address: Dict[str, Any] = field(default_factory=dict)
    parsed_address: Dict[str, Any] = field(default_factory=dict)
    enriched_address: Dict[str, Any] = field(default_factory=dict)

    # Confidence and review
    confidence_score: ConfidenceScore = field(default_factory=ConfidenceScore)
    review_status: ReviewStatus = ReviewStatus.AUTO
    reviewed_by: Optional[UUID] = None
    reviewed_at: Optional[datetime] = None
    review_notes: Optional[str] = None

    # Geometry for spatial queries
    geometry: Optional[str] = None  # WKT format

    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def is_high_confidence(self) -> bool:
        return self.confidence_score.tier == ConfidenceTier.HIGH

    def needs_review(self) -> bool:
        return self.review_status == ReviewStatus.NEEDS_REVIEW

    def update_review(self, user_id: UUID, status: ReviewStatus, notes: Optional[str] = None) -> None:
        self.review_status = status
        self.reviewed_by = user_id
        self.reviewed_at = datetime.utcnow()
        self.review_notes = notes
        self.updated_at = datetime.utcnow()