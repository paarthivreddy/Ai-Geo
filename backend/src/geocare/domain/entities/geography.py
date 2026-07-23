"""Geography entities for GeoCare AI."""

from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID, uuid4


@dataclass
class PincodeRecord:
    """PIN code directory record from India Post."""

    pincode: str
    office_name: str
    office_type: str  # head, sub, branch
    delivery_status: str  # delivery, non_delivery
    district: str
    state: str
    taluk: Optional[str] = None
    circle: Optional[str] = None
    region: Optional[str] = None
    division: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    localities: list[str] = field(default_factory=list)
    source_version: str = ""

    def to_context(self) -> "GeoContext":
        return GeoContext(
            pincode=self.pincode,
            district=self.district,
            state=self.state,
            taluk=self.taluk,
        )

    def to_dict(self) -> dict:
        return {
            "pincode": self.pincode,
            "office_name": self.office_name,
            "office_type": self.office_type,
            "delivery_status": self.delivery_status,
            "district": self.district,
            "state": self.state,
            "taluk": self.taluk,
            "circle": self.circle,
            "region": self.region,
            "division": self.division,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "localities": self.localities,
            "source_version": self.source_version,
        }


@dataclass
class PincodeResolution:
    """Result of PIN code resolution."""

    pincode: str
    district: str
    state: str
    taluk: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    confidence: int = 100
    source: str = "india_post"

    def to_context(self) -> "GeoContext":
        return GeoContext(
            pincode=self.pincode,
            district=self.district,
            state=self.state,
            taluk=self.taluk,
        )

    def to_dict(self) -> dict:
        return {
            "pincode": self.pincode,
            "district": self.district,
            "state": self.state,
            "taluk": self.taluk,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "confidence": self.confidence,
            "source": self.source,
        }


@dataclass
class LocalityRecord:
    """Locality dictionary record (India Post + OSM + Census)."""

    id: int
    canonical_name: str
    aliases: list[str] = field(default_factory=list)
    pincode: str = ""
    city: str = ""
    district: str = ""
    state: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    population: Optional[int] = None
    source: str = "merged"
    source_version: str = ""


@dataclass
class LocalityMatch:
    """Result of locality fuzzy matching."""

    canonical_name: str
    pincode: str
    city: str
    district: str
    state: str
    score: int
    method: str
    source: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    def to_context(self) -> "GeoContext":
        return GeoContext(
            locality=self.canonical_name,
            pincode=self.pincode,
            city=self.city,
            district=self.district,
            state=self.state,
        )

    def to_dict(self) -> dict:
        return {
            "canonical_name": self.canonical_name,
            "pincode": self.pincode,
            "city": self.city,
            "district": self.district,
            "state": self.state,
            "score": self.score,
            "method": self.method,
            "source": self.source,
            "latitude": self.latitude,
            "longitude": self.longitude,
        }


@dataclass
class GeoContext:
    """Geographic context for disambiguation."""

    pincode: Optional[str] = None
    locality: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    taluk: Optional[str] = None

    def merge(self, other: "GeoContext") -> "GeoContext":
        return GeoContext(
            pincode=self.pincode or other.pincode,
            locality=self.locality or other.locality,
            city=self.city or other.city,
            district=self.district or other.district,
            state=self.state or other.state,
            taluk=self.taluk or other.taluk,
        )

    def has_context(self) -> bool:
        return any(
            [self.pincode, self.locality, self.city, self.district, self.state, self.taluk]
        )


@dataclass
class EnrichmentResult:
    """Result of hierarchy enrichment from PIN code."""

    state: str
    district: str
    cities: list[str] = field(default_factory=list)
    taluk: Optional[str] = None
    confidence: int = 95


@dataclass
class ParsedAddress:
    """Structured address components from libpostal."""

    house_number: Optional[str] = None
    street: Optional[str] = None
    locality: Optional[str] = None
    sublocality: Optional[str] = None
    village: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    country: str = "India"

    def to_dict(self) -> dict:
        return {
            "house_number": self.house_number,
            "street": self.street,
            "locality": self.locality,
            "sublocality": self.sublocality,
            "village": self.village,
            "city": self.city,
            "district": self.district,
            "state": self.state,
            "pincode": self.pincode,
            "country": self.country,
        }


@dataclass
class EnrichedAddress:
    """Fully enriched and standardized address."""

    line1: str
    line2: Optional[str] = None
    locality: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    country: str = "India"
    formatted: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "line1": self.line1,
            "line2": self.line2,
            "locality": self.locality,
            "city": self.city,
            "district": self.district,
            "state": self.state,
            "pincode": self.pincode,
            "country": self.country,
            "formatted": self.formatted,
            "latitude": self.latitude,
            "longitude": self.longitude,
        }


@dataclass
class ValidationResult:
    """Geography validation result."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class CensusHierarchyRecord:
    """Census hierarchy record."""

    state_code: str = ""
    state_name: str = ""
    district_code: Optional[str] = None
    district_name: Optional[str] = None
    subdistrict_code: Optional[str] = None
    subdistrict_name: Optional[str] = None
    village_code: Optional[str] = None
    village_name: Optional[str] = None
    level: str = ""
    population: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    source_version: Optional[str] = None