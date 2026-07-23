"""Job management API routes."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from geocare.config.container import container
from geocare.application.use_cases.processing import ProcessUseCase
from geocare.application.use_cases.reporting import ReportUseCase
from geocare.application.use_cases.export import ExportUseCase
from geocare.application.use_cases.audit import AuditUseCase
from geocare.presentation.api.deps import get_current_user
from geocare.domain.entities.user import User
from geocare.domain.entities.job import JobStatus

router = APIRouter(prefix="/jobs", tags=["Jobs"])


# Request/Response Models
class JobCreateRequest(BaseModel):
    file_id: UUID
    column_mapping: dict
    chunk_size: int = 50000


class JobResponse(BaseModel):
    job_id: UUID
    filename: str
    status: JobStatus
    progress_pct: float
    total_rows: int
    processed_rows: int
    succeeded_rows: int
    failed_rows: int
    manual_review_rows: int
    total_chunks: int
    completed_chunks: list[int]
    failed_chunks: list[int]
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    created_at: str
    updated_at: str


class JobListResponse(BaseModel):
    jobs: list[JobResponse]
    total: int
    limit: int
    offset: int


class JobCancelRequest(BaseModel):
    reason: Optional[str] = None


# Routes
@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    request: JobCreateRequest,
    current_user: User = Depends(get_current_user),
    process_uc: ProcessUseCase = Depends(container.application.process_use_case),
) -> JobResponse:
    """Create and start a processing job."""
    job = await process_uc.create_and_start_job(
        file_id=request.file_id,
        column_mapping=request.column_mapping,
        chunk_size=request.chunk_size,
        user_id=current_user.id,
    )
    return _to_job_response(job)


@router.get("", response_model=JobListResponse)
async def list_jobs(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    process_uc: ProcessUseCase = Depends(container.application.process_use_case),
) -> JobListResponse:
    """List jobs for current user with pagination."""
    jobs, total = await process_uc.list_jobs(
        user_id=current_user.id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return JobListResponse(
        jobs=[_to_job_response(j) for j in jobs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    process_uc: ProcessUseCase = Depends(container.application.process_use_case),
) -> JobResponse:
    """Get job details by ID."""
    job = await process_uc.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    # Check ownership
    if job.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this job",
        )
    return _to_job_response(job)


@router.get("/{job_id}/stream")
async def stream_job_progress(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    process_uc: ProcessUseCase = Depends(container.application.process_use_case),
):
    """Server-Sent Events stream for real-time job progress."""
    job = await process_uc.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    if job.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized",
        )

    return await process_uc.stream_progress(job_id)


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: UUID,
    request: JobCancelRequest,
    current_user: User = Depends(get_current_user),
    process_uc: ProcessUseCase = Depends(container.application.process_use_case),
) -> dict:
    """Cancel a running job."""
    job = await process_uc.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    if job.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized",
        )
    if job.is_terminal():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job is already {job.status.value}",
        )

    await process_uc.cancel_job(job_id, request.reason)
    return {"message": "Job cancelled"}


@router.post("/{job_id}/retry")
async def retry_job(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    process_uc: ProcessUseCase = Depends(container.application.process_use_case),
) -> dict:
    """Retry a failed job from failed chunks."""
    job = await process_uc.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    if job.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized",
        )
    if not job.can_retry():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job cannot be retried",
        )

    new_job = await process_uc.retry_job(job_id)
    return {"job_id": str(new_job.id), "message": "Job retry started"}


@router.get("/{job_id}/report")
async def get_job_report(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    report_uc: ReportUseCase = Depends(container.application.report_use_case),
) -> dict:
    """Get before/after quality report for a job."""
    job = await container.infrastructure.repositories.job_repository.get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    if job.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized",
        )

    report = await report_uc.generate_report(job_id)
    return report.to_dict()


@router.get("/{job_id}/export")
async def export_job_results(
    job_id: UUID,
    format: str = Query("csv", pattern="^(csv|xlsx|parquet)$"),
    confidence_tiers: Optional[str] = Query(None, description="Comma-separated tiers: high,medium,low,unverified"),
    include_audit: bool = False,
    include_original: bool = True,
    current_user: User = Depends(get_current_user),
    export_uc: ExportUseCase = Depends(container.application.export_use_case),
):
    """Export enriched results as CSV, Excel, or Parquet."""
    job = await container.infrastructure.repositories.job_repository.get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    if job.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized",
        )

    tiers = confidence_tiers.split(",") if confidence_tiers else None

    file_path = await export_uc.export_job(
        job_id=job_id,
        format=format,
        confidence_tiers=tiers,
        include_audit=include_audit,
        include_original=include_original,
    )

    # Return presigned URL or file response
    from geocare.infrastructure.storage.s3_client import S3StorageClient
    s3_client = container.infrastructure.file_storage
    url = await s3_client.generate_presigned_url(file_path, expiration=3600)
    return {"download_url": url, "expires_in": 3600}


@router.get("/{job_id}/audit")
async def get_job_audit(
    job_id: UUID,
    limit: int = Query(1000, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    audit_uc: AuditUseCase = Depends(container.application.audit_use_case),
) -> dict:
    """Get audit trail for a job."""
    job = await container.infrastructure.repositories.job_repository.get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    if job.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized",
        )

    summary = await audit_uc.get_job_audit_summary(job_id)
    entries = await audit_uc.get_job_audit_entries(job_id, limit, offset)

    return {
        "summary": summary,
        "entries": [
            {
                "id": str(e.id),
                "record_id": str(e.record_id),
                "field_name": e.field_name,
                "old_value": e.old_value,
                "new_value": e.new_value,
                "processing_method": e.processing_method.value,
                "confidence": e.confidence,
                "source_dataset": e.source_dataset.value,
                "user_id": str(e.user_id) if e.user_id else None,
                "created_at": e.created_at.isoformat(),
            }
            for e in entries
        ],
        "limit": limit,
        "offset": offset,
    }


def _to_job_response(job) -> JobResponse:
    """Convert job entity to response model."""
    return JobResponse(
        job_id=job.id,
        filename=job.filename,
        status=job.status,
        progress_pct=job.progress_pct,
        total_rows=job.total_rows,
        processed_rows=job.processed_rows,
        succeeded_rows=job.succeeded_rows,
        failed_rows=job.failed_rows,
        manual_review_rows=job.manual_review_rows,
        total_chunks=job.total_chunks,
        completed_chunks=job.completed_chunks,
        failed_chunks=job.failed_chunks,
        started_at=job.started_at.isoformat() if job.started_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        error_message=job.error_message,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
    )