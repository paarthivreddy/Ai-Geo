"""Repository port interfaces for GeoCare AI."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Optional, List
from uuid import UUID

from geocare.domain.entities.job import ProcessingJob, JobChunk, JobQualityStats
from geocare.domain.entities.record import PatientRecord
from geocare.domain.entities.audit import AuditEntry
from geocare.domain.entities.user import User
from geocare.domain.entities.geography import (
    PincodeRecord,
    LocalityRecord,
    CensusHierarchyRecord,
)
from geocare.infrastructure.storage import FileStoragePort


class JobRepository(ABC):
    """Port for processing job persistence."""

    @abstractmethod
    async def create(self, job: ProcessingJob) -> ProcessingJob:
        """Create a new processing job."""
        ...

    @abstractmethod
    async def get(self, job_id: UUID) -> Optional[ProcessingJob]:
        """Get job by ID."""
        ...

    @abstractmethod
    async def get_by_user(
        self,
        user_id: UUID,
        limit: int = 20,
        offset: int = 0,
        status: Optional[str] = None,
    ) -> list[ProcessingJob]:
        """Get jobs for a user with pagination."""
        ...

    @abstractmethod
    async def update(self, job: ProcessingJob) -> ProcessingJob:
        """Update job (status, progress, etc.)."""
        ...

    @abstractmethod
    async def delete(self, job_id: UUID) -> bool:
        """Delete a job (soft delete)."""
        ...

    @abstractmethod
    async def count_by_user(self, user_id: UUID) -> int:
        """Count total jobs for a user."""
        ...


class ChunkRepository(ABC):
    """Port for job chunk persistence."""

    @abstractmethod
    async def create_batch(self, chunks: list[JobChunk]) -> list[JobChunk]:
        """Create multiple chunks."""
        ...

    @abstractmethod
    async def get_pending(self, job_id: UUID) -> list[JobChunk]:
        """Get pending chunks for a job."""
        ...

    @abstractmethod
    async def get_by_index(self, job_id: UUID, chunk_index: int) -> Optional[JobChunk]:
        """Get chunk by index."""
        ...

    @abstractmethod
    async def update(self, chunk: JobChunk) -> JobChunk:
        """Update chunk status."""
        ...

    @abstractmethod
    async def count_by_status(self, job_id: UUID) -> dict[str, int]:
        """Count chunks by status for a job."""
        ...


class RecordRepository(ABC):
    """Port for patient record persistence."""

    @abstractmethod
    async def bulk_create(self, records: list[PatientRecord]) -> list[PatientRecord]:
        """Bulk insert patient records."""
        ...

    @abstractmethod
    async def get_batch(
        self,
        job_id: UUID,
        offset: int,
        limit: int,
        review_status: Optional[str] = None,
        confidence_tier: Optional[str] = None,
    ) -> list[PatientRecord]:
        """Get paginated records for a job."""
        ...

    @abstractmethod
    async def get_by_id(self, record_id: UUID) -> Optional[PatientRecord]:
        """Get single record by ID."""
        ...

    @abstractmethod
    async def update(self, record: PatientRecord) -> PatientRecord:
        """Update record (enriched address, confidence, review status)."""
        ...

    @abstractmethod
    async def bulk_update(self, records: list[PatientRecord]) -> list[PatientRecord]:
        """Bulk update records."""
        ...

    @abstractmethod
    async def count_by_status(self, job_id: UUID) -> dict[str, int]:
        """Count records by review status for a job."""
        ...

    @abstractmethod
    async def count_by_confidence(self, job_id: UUID) -> dict[str, int]:
        """Count records by confidence tier for a job."""
        ...

    @abstractmethod
    async def stream_for_export(
        self,
        job_id: UUID,
        batch_size: int = 10000,
    ) -> AsyncGenerator[list[PatientRecord], None]:
        """Stream records for export (memory efficient)."""
        ...


class AuditRepository(ABC):
    """Port for audit trail persistence."""

    @abstractmethod
    async def bulk_create(self, entries: list[AuditEntry]) -> None:
        """Bulk insert audit entries."""
        ...

    @abstractmethod
    async def get_for_record(self, record_id: UUID) -> list[AuditEntry]:
        """Get audit trail for a specific record."""
        ...

    @abstractmethod
    async def get_for_job(
        self,
        job_id: UUID,
        limit: int = 10000,
        offset: int = 0,
    ) -> list[AuditEntry]:
        """Get audit trail for a job."""
        ...

    @abstractmethod
    async def stream_for_job(
        self,
        job_id: UUID,
        batch_size: int = 10000,
    ) -> AsyncGenerator[list[AuditEntry], None]:
        """Stream audit entries for export."""
        ...


class UserRepository(ABC):
    """Port for user persistence."""

    @abstractmethod
    async def create(self, user: User) -> User:
        """Create a new user."""
        ...

    @abstractmethod
    async def get(self, user_id: UUID) -> Optional[User]:
        """Get user by ID."""
        ...

    @abstractmethod
    async def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        ...

    @abstractmethod
    async def update(self, user: User) -> User:
        """Update user."""
        ...

    @abstractmethod
    async def list(
        self,
        limit: int = 50,
        offset: int = 0,
        role: Optional[str] = None,
    ) -> list[User]:
        """List users with pagination."""
        ...

    @abstractmethod
    async def count(self, role: Optional[str] = None) -> int:
        """Count users."""
        ...


class PincodeRepository(ABC):
    """Port for PIN code reference data."""

    @abstractmethod
    async def load_batch(self, records: list[PincodeRecord]) -> None:
        """Bulk load PIN code records."""
        ...

    @abstractmethod
    async def get(self, pincode: str) -> Optional[PincodeRecord]:
        """Get PIN code record by code."""
        ...

    @abstractmethod
    async def search_by_district_state(
        self, district: str, state: str
    ) -> list[PincodeRecord]:
        """Search PIN codes by district and state."""
        ...

    @abstractmethod
    async def get_localities_for_pincode(self, pincode: str) -> list[str]:
        """Get localities served by a PIN code."""
        ...

    @abstractmethod
    async def count(self) -> int:
        """Count total PIN codes."""
        ...

    @abstractmethod
    async def truncate(self) -> None:
        """Truncate table for reload."""
        ...

    @abstractmethod
    async def get_all(self) -> list[PincodeRecord]:
        """Get all PIN code records."""
        ...


class LocalityRepository(ABC):
    """Port for locality dictionary."""

    @abstractmethod
    async def load_batch(self, records: list[LocalityRecord]) -> None:
        """Bulk load locality records."""
        ...

    @abstractmethod
    async def get_by_canonical(self, name: str) -> Optional[LocalityRecord]:
        """Get locality by canonical name."""
        ...

    @abstractmethod
    async def search_by_alias(self, alias: str) -> list[LocalityRecord]:
        """Search localities by alias (fuzzy fallback)."""
        ...

    @abstractmethod
    async def get_by_pincode(self, pincode: str) -> list[LocalityRecord]:
        """Get localities for a PIN code."""
        ...

    @abstractmethod
    async def search_by_city_district(
        self, city: str, district: str, state: str
    ) -> list[LocalityRecord]:
        """Search localities by city/district/state context."""
        ...

    @abstractmethod
    async def count(self) -> int:
        """Count total localities."""
        ...

    @abstractmethod
    async def truncate(self) -> None:
        """Truncate table for reload."""
        ...

    @abstractmethod
    async def get_all(self) -> list[LocalityRecord]:
        """Get all locality records."""
        ...


class CensusRepository(ABC):
    """Port for Census hierarchy data."""

    @abstractmethod
    async def load_batch(self, records: list[CensusHierarchyRecord]) -> None:
        """Bulk load census records."""
        ...

    @abstractmethod
    async def get_state(self, code: str) -> Optional[CensusHierarchyRecord]:
        """Get state by code."""
        ...

    @abstractmethod
    async def get_district(self, code: str) -> Optional[CensusHierarchyRecord]:
        """Get district by code."""
        ...

    @abstractmethod
    async def get_subdistrict(self, code: str) -> Optional[CensusHierarchyRecord]:
        """Get sub-district by code."""
        ...

    @abstractmethod
    async def search_by_name(
        self, name: str, level: Optional[str] = None
    ) -> list[CensusHierarchyRecord]:
        """Search by name with optional level filter."""
        ...

    @abstractmethod
    async def get_all(self) -> list[CensusHierarchyRecord]:
        """Get all census records."""
        ...

    @abstractmethod
    async def get_hierarchy_from_pincode(
        self, pincode: str
    ) -> Optional[dict]:
        """Get full hierarchy (state, district, subdistrict, villages) from PIN."""
        ...

    @abstractmethod
    async def truncate(self) -> None:
        """Truncate table for reload."""
        ...


class PostGISRepository(ABC):
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
        """Validate address hierarchy via point-in-polygon.
        Returns (is_valid, list_of_errors).
        """
        ...

    @abstractmethod
    async def get_choropleth_data(
        self,
        job_id: UUID,
        level: str,  # "state" or "district"
    ) -> list[dict]:
        """Get aggregated record counts by boundary for heatmap."""
        ...

    @abstractmethod
    async def find_containing_boundary(
        self,
        latitude: float,
        longitude: float,
        admin_level: int,
    ) -> Optional[dict]:
        """Find containing boundary at given admin level."""
        ...


class GeographyEnginePort(ABC):
    """Port for the main geography enrichment engine."""

    @abstractmethod
    async def enrich_address(
        self,
        address_input: dict,
        parsed_address: dict,
    ) -> tuple[dict, dict]:
        """Enrich address and return (enriched_address, confidence_score)."""
        ...

    @abstractmethod
    async def parse_address(self, text: str) -> dict:
        """Parse raw address text into structured components."""
        ...

    @abstractmethod
    async def resolve_pincode(self, pincode: str) -> Optional[dict]:
        """Resolve PIN code to district/state."""
        ...

    @abstractmethod
    async def match_locality(
        self, name: str, context: Optional[dict] = None
    ) -> Optional[dict]:
        """Match locality name with context."""
        ...

    @abstractmethod
    def get_dataset_version(self) -> str:
        """Get current geography dataset version."""
        ...