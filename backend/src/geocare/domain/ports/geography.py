"""Geography engine port interface."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from geocare.domain.entities.geography import (
    PincodeResolution,
    LocalityMatch,
    GeoContext,
    EnrichmentResult,
    ParsedAddress,
    EnrichedAddress,
    ValidationResult,
)


class GeographyEnginePort(ABC):
    """Port for the main geography enrichment engine."""

    @abstractmethod
    async def enrich_address(
        self,
        address_input: Dict[str, Any],
        parsed_address: Dict[str, Any],
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """Enrich address and return (enriched_address, confidence_score)."""
        ...

    @abstractmethod
    async def parse_address(self, text: str) -> Dict[str, Any]:
        """Parse raw address text into structured components."""
        ...

    @abstractmethod
    async def resolve_pincode(self, pincode: str) -> Optional[Dict[str, Any]]:
        """Resolve PIN code to district/state."""
        ...

    @abstractmethod
    async def match_locality(
        self, name: str, context: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Match locality name with context."""
        ...

    @abstractmethod
    def get_dataset_version(self) -> str:
        """Get current geography dataset version."""
        ...


class PincodeIndexPort(ABC):
    """Port for PIN code index operations."""

    @abstractmethod
    def load(self, df) -> None:
        """Build indexes from DataFrame."""
        ...

    @abstractmethod
    def resolve(self, pincode: str) -> Optional[PincodeResolution]:
        """Exact PIN lookup with validation."""
        ...

    @abstractmethod
    def reverse_lookup(
        self,
        locality: str,
        district: Optional[str] = None,
        state: Optional[str] = None,
    ) -> list[PincodeResolution]:
        """Find candidate PINs for a locality."""
        ...


class LocalityFuzzyIndexPort(ABC):
    """Port for locality fuzzy matching."""

    @abstractmethod
    async def load(self) -> None:
        """Load localities from repository."""
        ...

    @abstractmethod
    async def match(
        self,
        query: str,
        context: Optional[GeoContext] = None,
        limit: int = 10,
    ) -> list[LocalityMatch]:
        """Match locality with multi-strategy search."""
        ...


class CensusHierarchyPort(ABC):
    """Port for Census hierarchy operations."""

    @abstractmethod
    async def load(self) -> None:
        """Load hierarchy from repository."""
        ...

    @abstractmethod
    def enrich_from_pincode(self, pincode: str) -> Optional[EnrichmentResult]:
        """Use PIN -> (District, State) to walk hierarchy."""
        ...

    @abstractmethod
    def search_by_name(
        self, name: str, level: Optional[str] = None
    ) -> list:
        """Search hierarchy by name."""
        ...


class ParserAdapterPort(ABC):
    """Port for address parsing adapter."""

    @abstractmethod
    def parse(self, address: str) -> ParsedAddress:
        """Parse address with libpostal and map to domain model."""
        ...

    @abstractmethod
    def expand_address(self, address: str) -> list[str]:
        """Generate address variations for better matching."""
        ...


class PostGISRepositoryPort(ABC):
    """Port for OSM PostGIS spatial queries."""

    @abstractmethod
    async def validate_hierarchy(
        self,
        latitude: float,
        longitude: float,
        expected_city: Optional[str] = None,
        expected_district: Optional[str] = None,
        expected_state: Optional[str] = None,
    ) -> tuple[bool, list[str]]:
        """Validate address hierarchy via point-in-polygon."""
        ...

    @abstractmethod
    async def get_choropleth_data(
        self,
        job_id: str,
        level: str,
    ) -> list[Dict[str, Any]]:
        """Get aggregated record counts by boundary for heatmap."""
        ...

    @abstractmethod
    async def find_containing_boundary(
        self,
        latitude: float,
        longitude: float,
        admin_level: int,
    ) -> Optional[Dict[str, Any]]:
        """Find containing boundary at given admin level."""
        ...

    @abstractmethod
    async def refresh_choropleth_views(self) -> None:
        """Refresh materialized views for choropleth."""
        ...