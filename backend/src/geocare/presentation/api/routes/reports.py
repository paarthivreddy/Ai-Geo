"""Reports API routes."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from geocare.config.container import container
from geocare.application.use_cases.reporting import ReportUseCase
from geocare.presentation.api.deps import get_current_user
from geocare.domain.entities.user import User

router = APIRouter(prefix="/reports", tags=["Reports"])


# Response Models
class QualityReportResponse(BaseModel):
    before: dict
    after: dict
    delta: dict
    confidence_distribution: dict[str, int]
    generated_at: str


class ReportListItem(BaseModel):
    job_id: UUID
    filename: str
    generated_at: str
    final_quality_score: float


# Routes
@router.get("/{job_id}", response_model=QualityReportResponse)
async def get_quality_report(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    report_uc: ReportUseCase = Depends(container.application.report_use_case),
) -> QualityReportResponse:
    """Get detailed quality report for a completed job."""
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
    if job.status.value != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Report only available for completed jobs",
        )

    report = await report_uc.generate_report(job_id)
    return QualityReportResponse(
        before=report.before,
        after=report.after,
        delta=report.delta,
        confidence_distribution=report.confidence_distribution,
        generated_at=report.generated_at.isoformat(),
    )


@router.get("", response_model=list[ReportListItem])
async def list_reports(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    report_uc: ReportUseCase = Depends(container.application.report_use_case),
) -> list[ReportListItem]:
    """List available quality reports for user's completed jobs."""
    jobs = await container.infrastructure.repositories.job_repository.get_by_user(
        user_id=current_user.id,
        limit=limit,
        offset=offset,
        status="completed",
    )

    return [
        ReportListItem(
            job_id=job.id,
            filename=job.filename,
            generated_at=job.completed_at.isoformat() if job.completed_at else "",
            final_quality_score=job.quality_stats.final_quality_score if job.quality_stats else 0,
        )
        for job in jobs
    ]


@router.get("/{job_id}/download")
async def download_report(
    job_id: UUID,
    format: str = Query("pdf", pattern="^(pdf|json|csv)$"),
    current_user: User = Depends(get_current_user),
    report_uc: ReportUseCase = Depends(container.application.report_use_case),
):
    """Download quality report as PDF, JSON, or CSV."""
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

    file_content = await report_uc.export_report(job_id, format)

    from fastapi.responses import Response
    media_types = {
        "pdf": "application/pdf",
        "json": "application/json",
        "csv": "text/csv",
    }
    return Response(
        content=file_content,
        media_type=media_types[format],
        headers={
            "Content-Disposition": f'attachment; filename="quality_report_{job_id}.{format}"'
        },
    )