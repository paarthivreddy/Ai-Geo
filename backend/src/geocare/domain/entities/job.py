"""Domain entities for GeoCare AI."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4


class JobStatus(str, Enum):
    """Processing job status states."""

    PENDING = "pending"
    PROFILING = "profiling"
    MAPPING = "mapping"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReviewStatus(str, Enum):
    """Record review status."""

    AUTO = "auto"
    NEEDS_REVIEW = "needs_review"
    MANUAL_VERIFIED = "manual_verified"
    REJECTED = "rejected"


@dataclass
class ColumnMapping:
    """User-confirmed column mapping for address fields."""

    patient_id: Optional[str] = None
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    landmark: Optional[str] = None
    pincode: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "patient_id": self.patient_id,
            "address_line_1": self.address_line_1,
            "address_line_2": self.address_line_2,
            "landmark": self.landmark,
            "pincode": self.pincode,
            "city": self.city,
            "district": self.district,
            "state": self.state,
            "country": self.country,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ColumnMapping":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class ChunkStatus(str, Enum):
    """Job chunk status."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class JobChunk:
    """Job chunk for batch processing."""

    id: UUID = field(default_factory=uuid4)
    job_id: UUID = field(default_factory=uuid4)
    chunk_index: int = 0
    storage_path: str = ""
    row_count: int = 0
    status: ChunkStatus = ChunkStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    error_message: Optional[str] = None
    worker_id: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class JobQualityStats:
    """Quality statistics for a processing job."""

    job_id: UUID = field(default_factory=uuid4)
    # Pre-processing metrics
    total_records: Optional[int] = None
    complete_addresses_before: Optional[int] = None
    missing_pincode_before: Optional[int] = None
    missing_locality_before: Optional[int] = None
    missing_city_before: Optional[int] = None
    missing_district_before: Optional[int] = None
    missing_state_before: Optional[int] = None
    invalid_addresses_before: Optional[int] = None
    duplicate_addresses_before: Optional[int] = None
    overall_quality_before: Optional[float] = None
    # Post-processing metrics
    pincodes_added: Optional[int] = None
    cities_added: Optional[int] = None
    districts_added: Optional[int] = None
    states_added: Optional[int] = None
    spell_corrections: Optional[int] = None
    improved_records: Optional[int] = None
    manual_review_records: Optional[int] = None
    final_quality_score: Optional[float] = None
    improvement_percentage: Optional[float] = None
    # Confidence distribution
    confidence_high: int = 0
    confidence_medium: int = 0
    confidence_low: int = 0
    confidence_unverified: int = 0
    # Timing
    profiling_time: Optional[float] = None
    processing_time: Optional[float] = None
    reporting_time: Optional[float] = None
    export_time: Optional[float] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ProcessingJob:
    """Processing job entity with lifecycle management."""

    id: UUID = field(default_factory=uuid4)
    user_id: UUID = field(default_factory=uuid4)
    filename: str = ""
    original_file_path: Optional[str] = None
    parquet_file_path: Optional[str] = None
    total_rows: int = 0
    total_columns: int = 0
    column_mapping: ColumnMapping = field(default_factory=ColumnMapping)
    detected_address_columns: list[str] = field(default_factory=list)
    status: JobStatus = JobStatus.PENDING
    progress_pct: float = 0.0
    processed_rows: int = 0
    succeeded_rows: int = 0
    failed_rows: int = 0
    manual_review_rows: int = 0
    chunk_size: int = 50000
    total_chunks: int = 0
    completed_chunks: list[int] = field(default_factory=list)
    failed_chunks: list[int] = field(default_factory=list)
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    quality_stats: Optional[JobQualityStats] = None

    def mark_profiling(self) -> None:
        self.status = JobStatus.PROFILING
        self.updated_at = datetime.utcnow()

    def mark_mapping(self) -> None:
        self.status = JobStatus.MAPPING
        self.updated_at = datetime.utcnow()

    def mark_queued(self, total_chunks: int) -> None:
        self.status = JobStatus.QUEUED
        self.total_chunks = total_chunks
        self.updated_at = datetime.utcnow()

    def mark_processing(self) -> None:
        self.status = JobStatus.PROCESSING
        if self.started_at is None:
            self.started_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def update_progress(
        self,
        processed: int,
        succeeded: int,
        failed: int,
        manual_review: int,
        chunk_index: int,
    ) -> None:
        self.processed_rows = processed
        self.succeeded_rows = succeeded
        self.failed_rows = failed
        self.manual_review_rows = manual_review
        if chunk_index not in self.completed_chunks:
            self.completed_chunks.append(chunk_index)
        if self.total_rows > 0:
            self.progress_pct = round((self.processed_rows / self.total_rows) * 100, 2)
        self.updated_at = datetime.utcnow()

    def mark_chunk_failed(self, chunk_index: int) -> None:
        if chunk_index not in self.failed_chunks:
            self.failed_chunks.append(chunk_index)
        self.updated_at = datetime.utcnow()

    def complete(self) -> None:
        self.status = JobStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        self.progress_pct = 100.0
        self.updated_at = datetime.utcnow()

    def fail(self, error: str) -> None:
        self.status = JobStatus.FAILED
        self.error_message = error
        self.completed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def cancel(self) -> None:
        self.status = JobStatus.CANCELLED
        self.completed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def can_retry(self) -> bool:
        return self.status in (JobStatus.FAILED, JobStatus.CANCELLED)

    def is_terminal(self) -> bool:
        return self.status in (
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        )


@dataclass
class PatientRecord:
    """Patient address record entity."""

    id: UUID = field(default_factory=uuid4)
    job_id: UUID = field(default_factory=uuid4)
    row_index: int = 0
    patient_id_hash: str = ""
    original_address: dict = field(default_factory=dict)
    normalized_address: dict = field(default_factory=dict)
    parsed_address: dict = field(default_factory=dict)
    enriched_address: dict = field(default_factory=dict)
    confidence_score: dict = field(default_factory=dict)
    confidence_tier: str = "unverified"
    match_method: str = "manual"
    review_status: ReviewStatus = ReviewStatus.AUTO
    reviewed_by: Optional[UUID] = None
    reviewed_at: Optional[datetime] = None
    review_notes: Optional[str] = None
    geometry: Optional[dict] = None  # GeoJSON Point
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def update_enriched(
        self,
        enriched: dict,
        confidence: dict,
        tier: str,
        method: str,
    ) -> None:
        self.enriched_address = enriched
        self.confidence_score = confidence
        self.confidence_tier = tier
        self.match_method = method
        self.updated_at = datetime.utcnow()

    def mark_reviewed(
        self,
        reviewer_id: UUID,
        status: ReviewStatus,
        notes: Optional[str] = None,
    ) -> None:
        self.review_status = status
        self.reviewed_by = reviewer_id
        self.reviewed_at = datetime.utcnow()
        self.review_notes = notes
        self.updated_at = datetime.utcnow()

    def needs_review(self) -> bool:
        return self.review_status == ReviewStatus.NEEDS_REVIEW

    def is_auto_approved(self) -> bool:
        return self.confidence_tier == "high" and self.review_status == ReviewStatus.AUTO