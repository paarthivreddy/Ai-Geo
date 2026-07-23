"""Quality metrics value objects for GeoCare AI."""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class QualityMetrics:
    """Data quality metrics for before/after comparison."""

    total_records: int = 0
    complete_addresses: int = 0
    missing_pincode: int = 0
    missing_locality: int = 0
    missing_city: int = 0
    missing_district: int = 0
    missing_state: int = 0
    invalid_addresses: int = 0
    duplicate_addresses: int = 0
    overall_quality_pct: float = 0.0

    @property
    def completeness_pct(self) -> float:
        if self.total_records == 0:
            return 0.0
        return (self.complete_addresses / self.total_records) * 100

    @property
    def pincode_fill_rate(self) -> float:
        if self.total_records == 0:
            return 0.0
        return ((self.total_records - self.missing_pincode) / self.total_records) * 100


@dataclass
class QualityDelta:
    """Delta between before and after quality metrics."""

    pincodes_added: int = 0
    cities_added: int = 0
    districts_added: int = 0
    states_added: int = 0
    spell_corrections: int = 0
    improved_records: int = 0
    manual_review_records: int = 0
    quality_improvement_pct: float = 0.0
    fill_rate: float = 0.0


@dataclass
class QualityReport:
    """Complete quality report with before/after comparison."""

    before: QualityMetrics = field(default_factory=QualityMetrics)
    after: QualityMetrics = field(default_factory=QualityMetrics)
    delta: QualityDelta = field(default_factory=QualityDelta)
    confidence_distribution: dict[str, int] = field(default_factory=dict)
    generated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "before": {
                "total_records": self.before.total_records,
                "complete_addresses": self.before.complete_addresses,
                "missing_pincode": self.before.missing_pincode,
                "missing_locality": self.before.missing_locality,
                "missing_city": self.before.missing_city,
                "missing_district": self.before.missing_district,
                "missing_state": self.before.missing_state,
                "invalid_addresses": self.before.invalid_addresses,
                "duplicate_addresses": self.before.duplicate_addresses,
                "overall_quality_pct": self.before.overall_quality_pct,
            },
            "after": {
                "pincodes_added": self.delta.pincodes_added,
                "cities_added": self.delta.cities_added,
                "districts_added": self.delta.districts_added,
                "states_added": self.delta.states_added,
                "spell_corrections": self.delta.spell_corrections,
                "improved_records": self.delta.improved_records,
                "manual_review_records": self.delta.manual_review_records,
                "final_quality_pct": self.after.overall_quality_pct,
            },
            "delta": {
                "quality_improvement_pct": self.delta.quality_improvement_pct,
                "fill_rate": self.delta.fill_rate,
            },
            "confidence_distribution": self.confidence_distribution,
        }