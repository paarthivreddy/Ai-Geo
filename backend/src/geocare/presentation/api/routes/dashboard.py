"""Dashboard and analytics API routes."""

from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from geocare.config.container import container
from geocare.presentation.api.deps import get_current_user
from geocare.domain.entities.user import User

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


# Response Models
class KPIMetrics(BaseModel):
    total_records: int
    processed_records: int
    pending_records: int
    failed_records: int
    manual_review_records: int
    success_rate: float
    data_quality_score: float
    avg_confidence: float
    total_processing_time_seconds: float


class QualityComparison(BaseModel):
    before: dict
    after: dict
    delta: dict


class ConfidenceDistribution(BaseModel):
    high: int
    medium: int
    low: int
    unverified: int


class StateDistribution(BaseModel):
    state: str
    record_count: int
    percentage: float


class DistrictDistribution(BaseModel):
    district: str
    state: str
    record_count: int
    percentage: float


class ProcessingPerformance(BaseModel):
    date: str
    jobs_processed: int
    records_processed: int
    avg_records_per_second: float
    avg_processing_time_seconds: float


class ErrorCategories(BaseModel):
    category: str
    count: int


# Routes
@router.get("/overview", response_model=KPIMetrics)
async def get_overview(
    current_user: User = Depends(get_current_user),
) -> KPIMetrics:
    """Get dashboard KPI metrics."""
    from geocare.infrastructure.persistence.repositories.job_repo import JobRepositoryImpl
    from geocare.infrastructure.persistence.repositories.record_repo import RecordRepositoryImpl
    from geocare.config.database import get_db_session

    async with get_db_session() as session:
        job_repo = JobRepositoryImpl(session)
        record_repo = RecordRepositoryImpl(session)

        # Get user's jobs
        jobs = await job_repo.get_by_user(current_user.id, limit=1000)

        total_records = sum(j.total_rows for j in jobs)
        processed_records = sum(j.processed_rows for j in jobs)
        pending_records = total_records - processed_records
        failed_records = sum(j.failed_rows for j in jobs)
        manual_review_records = sum(j.manual_review_rows for j in jobs)

        # Calculate success rate
        completed_jobs = [j for j in jobs if j.is_terminal()]
        success_rate = (
            (len([j for j in completed_jobs if j.status.value == "completed"]) / len(completed_jobs) * 100)
            if completed_jobs else 0
        )

        # Get quality stats from completed jobs
        quality_scores = []
        confidence_scores = []
        total_time = 0

        for job in completed_jobs:
            if job.quality_stats:
                if job.quality_stats.final_quality_score:
                    quality_scores.append(job.quality_stats.final_quality_score)
                if job.quality_stats.confidence_high is not None:
                    # Calculate weighted average confidence
                    total = (job.quality_stats.confidence_high +
                            job.quality_stats.confidence_medium +
                            job.quality_stats.confidence_low +
                            job.quality_stats.confidence_unverified)
                    if total > 0:
                        avg_conf = (
                            job.quality_stats.confidence_high * 92.5 +
                            job.quality_stats.confidence_medium * 72 +
                            job.quality_stats.confidence_low * 49.5 +
                            job.quality_stats.confidence_unverified * 20
                        ) / total
                        confidence_scores.append(avg_conf)
                if job.quality_stats.processing_time:
                    total_time += job.quality_stats.processing_time

        return KPIMetrics(
            total_records=total_records,
            processed_records=processed_records,
            pending_records=pending_records,
            failed_records=failed_records,
            manual_review_records=manual_review_records,
            success_rate=round(success_rate, 2),
            data_quality_score=round(sum(quality_scores) / len(quality_scores), 2) if quality_scores else 0,
            avg_confidence=round(sum(confidence_scores) / len(confidence_scores), 2) if confidence_scores else 0,
            total_processing_time_seconds=round(total_time, 2),
        )


@router.get("/quality", response_model=QualityComparison)
async def get_quality_comparison(
    job_id: Optional[UUID] = Query(None),
    current_user: User = Depends(get_current_user),
) -> QualityComparison:
    """Get before/after quality comparison for a job or all jobs."""
    from geocare.infrastructure.persistence.repositories.job_repo import JobRepositoryImpl
    from geocare.config.database import get_db_session

    async with get_db_session() as session:
        job_repo = JobRepositoryImpl(session)

        if job_id:
            job = await job_repo.get(job_id)
            if not job or (job.user_id != current_user.id and current_user.role != "admin"):
                raise HTTPException(status_code=403, detail="Not authorized")
            jobs = [job]
        else:
            jobs = await job_repo.get_by_user(current_user.id, limit=100)

        # Aggregate quality stats
        if not jobs:
            return QualityComparison(before={}, after={}, delta={})

        total_records = sum(j.total_rows for j in jobs if j.quality_stats)
        before_complete = sum(j.quality_stats.complete_addresses_before or 0 for j in jobs)
        before_missing_pincode = sum(j.quality_stats.missing_pincode_before or 0 for j in jobs)
        before_missing_locality = sum(j.quality_stats.missing_locality_before or 0 for j in jobs)
        before_missing_city = sum(j.quality_stats.missing_city_before or 0 for j in jobs)
        before_missing_district = sum(j.quality_stats.missing_district_before or 0 for j in jobs)
        before_missing_state = sum(j.quality_stats.missing_state_before or 0 for j in jobs)
        before_invalid = sum(j.quality_stats.invalid_addresses_before or 0 for j in jobs)
        before_duplicates = sum(j.quality_stats.duplicate_addresses_before or 0 for j in jobs)
        before_quality = sum(j.quality_stats.overall_quality_before or 0 for j in jobs) / len(jobs) if jobs else 0

        after_pincodes = sum(j.quality_stats.pincodes_added or 0 for j in jobs)
        after_cities = sum(j.quality_stats.cities_added or 0 for j in jobs)
        after_districts = sum(j.quality_stats.districts_added or 0 for j in jobs)
        after_states = sum(j.quality_stats.states_added or 0 for j in jobs)
        after_corrections = sum(j.quality_stats.spell_corrections or 0 for j in jobs)
        after_improved = sum(j.quality_stats.improved_records or 0 for j in jobs)
        after_review = sum(j.quality_stats.manual_review_records or 0 for j in jobs)
        after_quality = sum(j.quality_stats.final_quality_score or 0 for j in jobs) / len(jobs) if jobs else 0

        return QualityComparison(
            before={
                "total_records": total_records,
                "complete_addresses": before_complete,
                "missing_pincode": before_missing_pincode,
                "missing_locality": before_missing_locality,
                "missing_city": before_missing_city,
                "missing_district": before_missing_district,
                "missing_state": before_missing_state,
                "invalid_addresses": before_invalid,
                "duplicate_addresses": before_duplicates,
                "quality_pct": round(before_quality, 2),
            },
            after={
                "pincodes_added": after_pincodes,
                "cities_added": after_cities,
                "districts_added": after_districts,
                "states_added": after_states,
                "spell_corrections": after_corrections,
                "improved_records": after_improved,
                "needs_review": after_review,
                "quality_pct": round(after_quality, 2),
            },
            delta={
                "quality_improvement": round(after_quality - before_quality, 2),
                "fill_rate": round((after_pincodes + after_cities + after_districts + after_states) / total_records * 100, 2) if total_records else 0,
            },
        )


@router.get("/confidence", response_model=ConfidenceDistribution)
async def get_confidence_distribution(
    job_id: Optional[UUID] = Query(None),
    current_user: User = Depends(get_current_user),
) -> ConfidenceDistribution:
    """Get confidence tier distribution."""
    from geocare.infrastructure.persistence.repositories.job_repo import JobRepositoryImpl
    from geocare.config.database import get_db_session

    async with get_db_session() as session:
        job_repo = JobRepositoryImpl(session)

        if job_id:
            job = await job_repo.get(job_id)
            if not job or (job.user_id != current_user.id and current_user.role != "admin"):
                raise HTTPException(status_code=403, detail="Not authorized")
            jobs = [job]
        else:
            jobs = await job_repo.get_by_user(current_user.id, limit=100)

        high = sum(j.quality_stats.confidence_high or 0 for j in jobs)
        medium = sum(j.quality_stats.confidence_medium or 0 for j in jobs)
        low = sum(j.quality_stats.confidence_low or 0 for j in jobs)
        unverified = sum(j.quality_stats.confidence_unverified or 0 for j in jobs)

        return ConfidenceDistribution(
            high=high,
            medium=medium,
            low=low,
            unverified=unverified,
        )


@router.get("/geography/states", response_model=list[StateDistribution])
async def get_state_distribution(
    job_id: Optional[UUID] = Query(None),
    limit: int = Query(36, ge=1, le=50),
    current_user: User = Depends(get_current_user),
) -> list[StateDistribution]:
    """Get record distribution by state."""
    from geocare.infrastructure.persistence.repositories.record_repo import RecordRepositoryImpl
    from geocare.config.database import get_db_session

    async with get_db_session() as session:
        record_repo = RecordRepositoryImpl(session)

        if job_id:
            jobs = [job_id]
        else:
            job_repo = JobRepositoryImpl(session)
            user_jobs = await job_repo.get_by_user(current_user.id, limit=100)
            jobs = [j.id for j in user_jobs]

        # Get state distribution from enriched_address JSONB
        from sqlalchemy import select, func, cast
        from sqlalchemy.dialects.postgresql import JSONB
        from geocare.infrastructure.persistence.models import PatientRecordModel

        query = (
            select(
                func.jsonb_extract_path_text(PatientRecordModel.enriched_address, 'state').label('state'),
                func.count(PatientRecordModel.id).label('count')
            )
            .where(PatientRecordModel.job_id.in_([str(j) for j in jobs]))
            .group_by('state')
            .order_by(func.count(PatientRecordModel.id).desc())
            .limit(limit)
        )

        result = await session.execute(query)
        rows = result.all()

        total = sum(r.count for r in rows) if rows else 1

        return [
            StateDistribution(
                state=r.state or "Unknown",
                record_count=r.count,
                percentage=round(r.count / total * 100, 2)
            )
            for r in rows
        ]


@router.get("/geography/districts", response_model=list[DistrictDistribution])
async def get_district_distribution(
    job_id: Optional[UUID] = Query(None),
    state: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
) -> list[DistrictDistribution]:
    """Get record distribution by district."""
    from geocare.infrastructure.persistence.repositories.record_repo import RecordRepositoryImpl
    from geocare.config.database import get_db_session
    from sqlalchemy import select, func
    from geocare.infrastructure.persistence.models import PatientRecordModel

    async with get_db_session() as session:
        if job_id:
            jobs = [job_id]
        else:
            job_repo = JobRepositoryImpl(session)
            user_jobs = await job_repo.get_by_user(current_user.id, limit=100)
            jobs = [j.id for j in user_jobs]

        query = (
            select(
                func.jsonb_extract_path_text(PatientRecordModel.enriched_address, 'district').label('district'),
                func.jsonb_extract_path_text(PatientRecordModel.enriched_address, 'state').label('state'),
                func.count(PatientRecordModel.id).label('count')
            )
            .where(PatientRecordModel.job_id.in_([str(j) for j in jobs]))
            .group_by('district', 'state')
            .order_by(func.count(PatientRecordModel.id).desc())
            .limit(limit)
        )

        if state:
            query = query.where(
                func.jsonb_extract_path_text(PatientRecordModel.enriched_address, 'state').ilike(state)
            )

        result = await session.execute(query)
        rows = result.all()

        total = sum(r.count for r in rows) if rows else 1

        return [
            DistrictDistribution(
                district=r.district or "Unknown",
                state=r.state or "Unknown",
                record_count=r.count,
                percentage=round(r.count / total * 100, 2)
            )
            for r in rows
        ]


@router.get("/performance", response_model=list[ProcessingPerformance])
async def get_processing_performance(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
) -> list[ProcessingPerformance]:
    """Get processing performance metrics over time."""
    from geocare.infrastructure.persistence.repositories.job_repo import JobRepositoryImpl
    from geocare.config.database import get_db_session
    from datetime import datetime, timedelta

    async with get_db_session() as session:
        job_repo = JobRepositoryImpl(session)
        jobs = await job_repo.get_by_user(current_user.id, limit=500)

        # Filter to completed jobs in time range
        cutoff = datetime.utcnow() - timedelta(days=days)
        completed_jobs = [
            j for j in jobs
            if j.status.value == "completed" and j.completed_at and j.completed_at >= cutoff
        ]

        # Group by date
        from collections import defaultdict
        daily = defaultdict(lambda: {"jobs": 0, "records": 0, "time": 0.0})

        for job in completed_jobs:
            date_key = job.completed_at.date().isoformat()
            daily[date_key]["jobs"] += 1
            daily[date_key]["records"] += job.processed_rows
            if job.quality_stats and job.quality_stats.processing_time:
                daily[date_key]["time"] += job.quality_stats.processing_time

        return [
            ProcessingPerformance(
                date=date,
                jobs_processed=stats["jobs"],
                records_processed=stats["records"],
                avg_records_per_second=round(stats["records"] / stats["time"], 2) if stats["time"] > 0 else 0,
                avg_processing_time_seconds=round(stats["time"] / stats["jobs"], 2) if stats["jobs"] > 0 else 0,
            )
            for date, stats in sorted(daily.items())
        ]


@router.get("/errors", response_model=list[ErrorCategories])
async def get_error_categories(
    job_id: Optional[UUID] = Query(None),
    current_user: User = Depends(get_current_user),
) -> list[ErrorCategories]:
    """Get error category breakdown."""
    from geocare.infrastructure.persistence.repositories.job_repo import JobRepositoryImpl
    from geocare.config.database import get_db_session

    async with get_db_session() as session:
        job_repo = JobRepositoryImpl(session)

        if job_id:
            job = await job_repo.get(job_id)
            if not job or (job.user_id != current_user.id and current_user.role != "admin"):
                raise HTTPException(status_code=403, detail="Not authorized")
            jobs = [job]
        else:
            jobs = await job_repo.get_by_user(current_user.id, limit=100)

        # Count failed chunks by error message
        from collections import Counter
        errors = Counter()
        for job in jobs:
            for chunk_idx in job.failed_chunks:
                # In a real implementation, you'd query job_chunks table for error_message
                errors["processing_error"] += 1

        return [
            ErrorCategories(category=cat, count=cnt)
            for cat, cnt in errors.most_common()
        ]


@router.get("/jobs/recent", response_model=list[dict])
async def get_recent_jobs(
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Get recent jobs for dashboard."""
    from geocare.infrastructure.persistence.repositories.job_repo import JobRepositoryImpl
    from geocare.config.database import get_db_session

    async with get_db_session() as session:
        job_repo = JobRepositoryImpl(session)
        jobs = await job_repo.get_by_user(current_user.id, limit=limit)

        return [
            {
                "job_id": str(j.id),
                "filename": j.filename,
                "status": j.status.value,
                "progress_pct": j.progress_pct,
                "total_rows": j.total_rows,
                "processed_rows": j.processed_rows,
                "created_at": j.created_at.isoformat(),
                "completed_at": j.completed_at.isoformat() if j.completed_at else None,
            }
            for j in jobs
        ]