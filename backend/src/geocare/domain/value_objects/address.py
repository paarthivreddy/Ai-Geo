"""Address value objects for GeoCare AI."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AddressInput:
    """Raw address input from user file."""

    line1: Optional[str] = None
    line2: Optional[str] = None
    landmark: Optional[str] = None
    pincode: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "line1": self.line1,
            "line2": self.line2,
            "landmark": self.landmark,
            "pincode": self.pincode,
            "city": self.city,
            "district": self.district,
            "state": self.state,
            "country": self.country,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AddressInput":
        return cls(
            line1=data.get("line1"),
            line2=data.get("line2"),
            landmark=data.get("landmark"),
            pincode=data.get("pincode"),
            city=data.get("city"),
            district=data.get("district"),
            state=data.get("state"),
            country=data.get("country"),
        )

    def get_concatenated(self) -> str:
        """Get full address as concatenated string for parsing."""
        parts = [
            self.line1,
            self.line2,
            self.landmark,
            self.city,
            self.district,
            self.state,
            self.pincode,
            self.country,
        ]
        return ", ".join(p for p in parts if p)


@dataclass
class ParsedAddress:
    """Structured address components from libpostal parsing."""

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

    def completeness_score(self) -> int:
        """Calculate parsing completeness as percentage."""
        fields = [
            self.house_number,
            self.street,
            self.locality,
            self.city,
            self.district,
            self.state,
            self.pincode,
        ]
        filled = sum(1 for f in fields if f)
        return int((filled / len(fields)) * 100)


@dataclass
class EnrichedAddress:
    """Fully enriched and canonical address."""

    line1: str
    line2: Optional[str] = None
    locality: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    country: str = "India"
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
            "latitude": self.latitude,
            "longitude": self.longitude,
        }

    def formatted(self) -> str:
        """Get formatted address string."""
        parts = [self.line1]
        if self.line2:
            parts.append(self.line2)
        if self.locality:
            parts.append(self.locality)
        if self.city:
            parts.append(self.city)
        if self.district:
            parts.append(self.district)
        if self.state:
            parts.append(self.state)
        if self.pincode:
            parts.append(self.pincode)
        parts.append(self.country)
        return ", ".join(parts)

    def has_coordinates(self) -> bool:
        return self.latitude is not None and self.longitude is not None