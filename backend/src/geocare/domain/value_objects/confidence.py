"""Confidence scoring value objects for GeoCare AI."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class ConfidenceWeights:
    """Weights for confidence scoring (must sum to 1.0)."""

    pincode_validity: float = 0.25
    locality_match: float = 0.25
    hierarchy_consistency: float = 0.20
    parsing_completeness: float = 0.15
    fuzzy_quality: float = 0.15

    def __post_init__(self) -> None:
        total = (
            self.pincode_validity
            + self.locality_match
            + self.hierarchy_consistency
            + self.parsing_completeness
            + self.fuzzy_quality
        )
        if abs(total - 1.0) > 0.001:
            raise ValueError("Weights must sum to 1.0")


@dataclass
class ConfidenceScore:
    """Confidence score breakdown and overall tier."""

    overall: int = 0
    pincode_validity: int = 0
    locality_match: int = 0
    hierarchy_consistency: int = 0
    parsing_completeness: int = 0
    fuzzy_quality: int = 0
    match_method: str = "manual"
    tier: str = "unverified"

    TIER_THRESHOLDS = {
        "high": 85,
        "medium": 60,
        "low": 40,
        "unverified": 0,
    }

    @classmethod
    def calculate(
        cls,
        pincode_score: int,
        locality_score: int,
        hierarchy_score: int,
        parsing_score: int,
        fuzzy_score: int,
        weights: Optional[ConfidenceWeights] = None,
    ) -> "ConfidenceScore":
        """Calculate weighted confidence score."""
        w = weights or ConfidenceWeights()

        overall = int(
            w.pincode_validity * pincode_score
            + w.locality_match * locality_score
            + w.hierarchy_consistency * hierarchy_score
            + w.parsing_completeness * parsing_score
            + w.fuzzy_quality * fuzzy_score
        )

        # Determine tier
        if overall >= 85:
            tier = "high"
        elif overall >= 60:
            tier = "medium"
        elif overall >= 40:
            tier = "low"
        else:
            tier = "unverified"

        # Determine primary match method
        if pincode_score == 100 and locality_score == 100:
            method = "exact"
        elif locality_score > 0:
            method = "fuzzy"
        elif pincode_score == 50:
            method = "inferred"
        else:
            method = "manual"

        return cls(
            overall=overall,
            pincode_validity=pincode_score,
            locality_match=locality_score,
            hierarchy_consistency=hierarchy_score,
            parsing_completeness=parsing_score,
            fuzzy_quality=fuzzy_score,
            match_method=method,
            tier=tier,
        )

    def is_auto_approved(self) -> bool:
        return self.tier == "high"

    def needs_review(self) -> bool:
        return self.tier in ("medium", "low")

    def requires_manual_verification(self) -> bool:
        return self.tier == "unverified"