"""SQLAlchemy ORM models for GeoCare AI."""

from datetime import datetime
from enum import Enum as PyEnum
from typing import Any, Optional

from sqlalchemy import (
    ARRAY,
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from geocare.config.database import Base


class UserRole(PyEnum):
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


class UserStatus(PyEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    LOCKED = "locked"


class UserModel(Base):
    """User account model."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(PGUUID(as_uuid=False), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(String(20), nullable=False, default=UserRole.VIEWER)
    status: Mapped[UserStatus] = mapped_column(String(20), nullable=False, default=UserStatus.ACTIVE)
    salt: Mapped[str] = mapped_column(String(32), nullable=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    jobs: Mapped[list["ProcessingJobModel"]] = relationship(back_populates="user", lazy="dynamic")

    __table_args__ = (
        Index("ix_users_status", "status", postgresql_where=status == UserStatus.ACTIVE.value),
    )


class JobStatus(PyEnum):
    PENDING = "pending"
    PROFILING = "profiling"
    MAPPING = "mapping"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProcessingJobModel(Base):
    """Processing job model."""

    __tablename__ = "processing_jobs"

    id: Mapped[str] = mapped_column(PGUUID(as_uuid=False), primary_key=True)
    user_id: Mapped[str] = mapped_column(PGUUID(as_uuid=False), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    original_file_path: Mapped[Optional[str]] = mapped_column(String(1000))
    parquet_file_path: Mapped[Optional[str]] = mapped_column(String(1000))
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_columns: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    column_mapping: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    detected_address_columns: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    status: Mapped[JobStatus] = mapped_column(String(20), default=JobStatus.PENDING, nullable=False, index=True)
    progress_pct: Mapped[float] = mapped_column(default=0.0, nullable=False)
    processed_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    succeeded_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    manual_review_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chunk_size: Mapped[int] = mapped_column(Integer, default=50000, nullable=False)
    total_chunks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_chunks: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list, nullable=False)
    failed_chunks: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user: Mapped["UserModel"] = relationship(back_populates="jobs")
    chunks: Mapped[list["JobChunkModel"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    records: Mapped[list["PatientRecordModel"]] = relationship(back_populates="job", lazy="dynamic")
    quality_stats: Mapped[Optional["JobQualityStatsModel"]] = relationship(back_populates="job", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_jobs_user_status", "user_id", "status"),
        Index("ix_jobs_created_at_desc", "created_at", postgresql_using="btree", postgresql_ops={"created_at": "DESC"}),
        Index("ix_jobs_status_active", "status", postgresql_where=status.in_([JobStatus.PROCESSING.value, JobStatus.QUEUED.value])),
    )


class ChunkStatus(PyEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobChunkModel(Base):
    """Job chunk model for batch processing."""

    __tablename__ = "job_chunks"

    id: Mapped[str] = mapped_column(PGUUID(as_uuid=False), primary_key=True)
    job_id: Mapped[str] = mapped_column(PGUUID(as_uuid=False), ForeignKey("processing_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[ChunkStatus] = mapped_column(String(20), default=ChunkStatus.PENDING, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    worker_id: Mapped[Optional[str]] = mapped_column(String(100))
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    job: Mapped["ProcessingJobModel"] = relationship(back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("job_id", "chunk_index", name="uq_job_chunk_index"),
        Index("ix_chunks_job_status", "job_id", "status"),
        Index("ix_chunks_worker", "worker_id", postgresql_where=status == ChunkStatus.PROCESSING.value),
    )


class ReviewStatus(PyEnum):
    AUTO = "auto"
    NEEDS_REVIEW = "needs_review"
    MANUAL_VERIFIED = "manual_verified"
    REJECTED = "rejected"


class ConfidenceTier(PyEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNVERIFIED = "unverified"


class MatchMethod(PyEnum):
    EXACT = "exact"
    FUZZY = "fuzzy"
    INFERRED = "inferred"
    MANUAL = "manual"


class PatientRecordModel(Base):
    """Patient record model - partitioned by job_id."""

    __tablename__ = "patient_records"

    id: Mapped[str] = mapped_column(PGUUID(as_uuid=False), primary_key=True)
    job_id: Mapped[str] = mapped_column(PGUUID(as_uuid=False), ForeignKey("processing_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    patient_id_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    original_address: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    normalized_address: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    parsed_address: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    enriched_address: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    confidence_score: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    confidence_tier: Mapped[ConfidenceTier] = mapped_column(String(20), default=ConfidenceTier.UNVERIFIED, nullable=False, index=True)
    match_method: Mapped[MatchMethod] = mapped_column(String(20), default=MatchMethod.MANUAL, nullable=False)
    review_status: Mapped[ReviewStatus] = mapped_column(String(20), default=ReviewStatus.AUTO, nullable=False, index=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(PGUUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    review_notes: Mapped[Optional[str]] = mapped_column(Text)
    geometry: Mapped[Optional[str]] = mapped_column(Text)  # WKT format
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    job: Mapped["ProcessingJobModel"] = relationship(back_populates="records")
    audit_entries: Mapped[list["AuditEntryModel"]] = relationship(back_populates="record", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_records_job_id", "job_id"),
        Index("ix_records_review_status", "review_status", postgresql_where=review_status != ReviewStatus.AUTO.value),
        Index("ix_records_confidence_tier", "confidence_tier"),
        Index("ix_records_patient_hash", "patient_id_hash"),
    )


class JobQualityStatsModel(Base):
    """Quality statistics for a processing job."""

    __tablename__ = "job_quality_stats"

    job_id: Mapped[str] = mapped_column(PGUUID(as_uuid=False), ForeignKey("processing_jobs.id", ondelete="CASCADE"), primary_key=True)

    # Pre-processing
    total_records: Mapped[Optional[int]] = mapped_column(Integer)
    complete_addresses_before: Mapped[Optional[int]] = mapped_column(Integer)
    missing_pincode_before: Mapped[Optional[int]] = mapped_column(Integer)
    missing_locality_before: Mapped[Optional[int]] = mapped_column(Integer)
    missing_city_before: Mapped[Optional[int]] = mapped_column(Integer)
    missing_district_before: Mapped[Optional[int]] = mapped_column(Integer)
    missing_state_before: Mapped[Optional[int]] = mapped_column(Integer)
    invalid_addresses_before: Mapped[Optional[int]] = mapped_column(Integer)
    duplicate_addresses_before: Mapped[Optional[int]] = mapped_column(Integer)
    overall_quality_before: Mapped[Optional[float]] = mapped_column(nullable=True)

    # Post-processing
    pincodes_added: Mapped[Optional[int]] = mapped_column(Integer)
    cities_added: Mapped[Optional[int]] = mapped_column(Integer)
    districts_added: Mapped[Optional[int]] = mapped_column(Integer)
    states_added: Mapped[Optional[int]] = mapped_column(Integer)
    spell_corrections: Mapped[Optional[int]] = mapped_column(Integer)
    improved_records: Mapped[Optional[int]] = mapped_column(Integer)
    manual_review_records: Mapped[Optional[int]] = mapped_column(Integer)
    final_quality_score: Mapped[Optional[float]] = mapped_column(nullable=True)
    improvement_percentage: Mapped[Optional[float]] = mapped_column(nullable=True)

    # Confidence distribution
    confidence_high: Mapped[int] = mapped_column(Integer, default=0)
    confidence_medium: Mapped[int] = mapped_column(Integer, default=0)
    confidence_low: Mapped[int] = mapped_column(Integer, default=0)
    confidence_unverified: Mapped[int] = mapped_column(Integer, default=0)

    # Timing
    profiling_time: Mapped[Optional[float]] = mapped_column(nullable=True)
    processing_time: Mapped[Optional[float]] = mapped_column(nullable=True)
    reporting_time: Mapped[Optional[float]] = mapped_column(nullable=True)
    export_time: Mapped[Optional[float]] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    job: Mapped["ProcessingJobModel"] = relationship(back_populates="quality_stats")


class ProcessingMethod(PyEnum):
    NORMALIZATION = "normalization"
    PARSING = "parsing"
    PIN_RESOLUTION = "pin_resolution"
    LOCALITY_MATCH = "locality_match"
    SPELL_CORRECTION = "spell_correction"
    HIERARCHY_ENRICHMENT = "hierarchy_enrichment"
    VALIDATION_CORRECTION = "validation_correction"
    MANUAL_OVERRIDE = "manual_override"


class DataSource(PyEnum):
    INDIA_POST = "india_post"
    OSM = "osm"
    CENSUS = "census"
    LIBPOSTAL = "libpostal"
    RAPIDFUZZ = "rapidfuzz"
    MANUAL = "manual"
    INFERRED = "inferred"


class AuditEntryModel(Base):
    """Audit trail entry model."""

    __tablename__ = "audit_entries"

    id: Mapped[str] = mapped_column(PGUUID(as_uuid=False), primary_key=True)
    record_id: Mapped[str] = mapped_column(PGUUID(as_uuid=False), ForeignKey("patient_records.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id: Mapped[str] = mapped_column(PGUUID(as_uuid=False), ForeignKey("processing_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    field_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    old_value: Mapped[Optional[str]] = mapped_column(Text)
    new_value: Mapped[Optional[str]] = mapped_column(Text)
    processing_method: Mapped[ProcessingMethod] = mapped_column(String(30), nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False)
    source_dataset: Mapped[DataSource] = mapped_column(String(20), nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(PGUUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True)

    record: Mapped["PatientRecordModel"] = relationship(back_populates="audit_entries")

    __table_args__ = (
        CheckConstraint("confidence BETWEEN 0 AND 100", name="ck_audit_confidence"),
        Index("ix_audit_created_at_desc", "created_at", postgresql_using="btree", postgresql_ops={"created_at": "DESC"}),
    )


# Geography reference models
class OfficeType(PyEnum):
    HEAD = "head"
    SUB = "sub"
    BRANCH = "branch"


class DeliveryStatus(PyEnum):
    DELIVERY = "delivery"
    NON_DELIVERY = "non_delivery"


class PincodeDirectoryModel(Base):
    """India Post PIN code directory."""

    __tablename__ = "pincode_directory"

    pincode: Mapped[str] = mapped_column(String(6), primary_key=True)
    office_name: Mapped[str] = mapped_column(String(255), nullable=False)
    office_type: Mapped[OfficeType] = mapped_column(String(20), nullable=False)
    delivery_status: Mapped[DeliveryStatus] = mapped_column(String(20), nullable=False)
    district: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    taluk: Mapped[Optional[str]] = mapped_column(String(100))
    circle: Mapped[Optional[str]] = mapped_column(String(100))
    region: Mapped[Optional[str]] = mapped_column(String(100))
    division: Mapped[Optional[str]] = mapped_column(String(100))
    latitude: Mapped[Optional[float]] = mapped_column(nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(nullable=True)
    localities: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    source_version: Mapped[str] = mapped_column(String(50), nullable=False)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("pincode ~ '^[1-8][0-9]{5}$'", name="ck_valid_pincode"),
        Index("ix_pincode_district_state", "district", "state"),
        Index("ix_pincode_taluk", "taluk"),
        Index("ix_pincode_geo", "latitude", "longitude", postgresql_where=latitude.isnot(None) & longitude.isnot(None)),
    )


class LocalitySource(PyEnum):
    INDIA_POST = "india_post"
    OSM = "osm"
    CENSUS = "census"
    MERGED = "merged"


class LocalityDictionaryModel(Base):
    """Unified locality dictionary (India Post + OSM + Census)."""

    __tablename__ = "locality_dictionary"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    pincode: Mapped[str] = mapped_column(String(6), ForeignKey("pincode_directory.pincode"), nullable=False, index=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    district: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    latitude: Mapped[Optional[float]] = mapped_column(nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(nullable=True)
    population: Mapped[Optional[int]] = mapped_column(BigInteger)
    source: Mapped[LocalitySource] = mapped_column(String(20), nullable=False)
    source_version: Mapped[Optional[str]] = mapped_column(String(50))
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "(latitude IS NULL AND longitude IS NULL) OR "
            "(latitude BETWEEN 6.0 AND 38.0 AND longitude BETWEEN 68.0 AND 98.0)",
            name="ck_valid_coords",
        ),
        Index("ix_locality_aliases_gin", "aliases", postgresql_using="gin"),
        Index("ix_locality_city_district", "city", "district"),
    )


class CensusHierarchyModel(Base):
    """Census 2011/2021 hierarchy."""

    __tablename__ = "census_hierarchy"

    state_code: Mapped[str] = mapped_column(String(2), primary_key=True)
    state_name: Mapped[str] = mapped_column(String(100), nullable=False)
    district_code: Mapped[Optional[str]] = mapped_column(String(4))
    district_name: Mapped[Optional[str]] = mapped_column(String(100))
    subdistrict_code: Mapped[Optional[str]] = mapped_column(String(6))
    subdistrict_name: Mapped[Optional[str]] = mapped_column(String(100))
    village_code: Mapped[Optional[str]] = mapped_column(String(8))
    village_name: Mapped[Optional[str]] = mapped_column(String(255))
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    population: Mapped[Optional[int]] = mapped_column(BigInteger)
    latitude: Mapped[Optional[float]] = mapped_column(nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(nullable=True)
    source_version: Mapped[Optional[str]] = mapped_column(String(50))
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_census_district", "district_code"),
        Index("ix_census_subdistrict", "subdistrict_code"),
        Index("ix_census_village", "village_code"),
        Index("ix_census_names", "state_name", "district_name", "village_name"),
    )


class DatasetVersionModel(Base):
    """Geography dataset version tracking."""

    __tablename__ = "geography_dataset_versions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dataset_name: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    checksum_sha256: Mapped[Optional[str]] = mapped_column(String(64))
    row_count: Mapped[Optional[int]] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(20), default="loading", nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    loaded_by: Mapped[Optional[str]] = mapped_column(PGUUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"))
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("dataset_name", "version", name="uq_dataset_version"),
        Index("ix_dataset_active", "dataset_name", "status", postgresql_where=status == "loaded"),
    )
