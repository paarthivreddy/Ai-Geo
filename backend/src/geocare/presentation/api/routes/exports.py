"""Export API routes."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from geocare.config.container import container
from geocare.application.use_cases.export import ExportUseCase
from geocare.presentation.api.deps import get_current_user
from geocare.domain.entities.user import User

router = APIRouter(prefix="/exports", tags=["Exports"])


# Response Models
class ExportRequest(BaseModel):
    job_id: UUID
    format: str = "csv"  # csv, xlsx, parquet
    confidence_tiers: Optional[list[str]] = None  # high, medium, low, unverified
    include_audit: bool = False
    include_original: bool = True


class ExportStatusResponse(BaseModel):
    export_id: UUID
    job_id: UUID
    format: str
    status: str  # pending, processing, completed, failed
    file_size_bytes: Optional[int] = None
    download_url: Optional[str] = None
    expires_at: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None


# Routes
@router.post("", response_model=ExportStatusResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_export(
    request: ExportRequest,
    current_user: User = Depends(get_current_user),
    export_uc: ExportUseCase = Depends(container.application.export_use_case),
) -> ExportStatusResponse:
    """Create an export job for processed results."""
    # Verify job ownership
    job_repo = container.infrastructure.repositories.job_repository
    job = await job_repo.get(request.job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    if job.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to export this job",
        )
    if job.status.value != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job must be completed before export",
        )

    export = await export_uc.create_export(
        job_id=request.job_id,
        format=request.format,
        confidence_tiers=request.confidence_tiers,
        include_audit=request.include_audit,
        include_original=request.include_original,
        user_id=current_user.id,
    )

    return ExportStatusResponse(
        export_id=export.id,
        job_id=export.job_id,
        format=export.format,
        status=export.status.value,
        created_at=export.created_at.isoformat(),
    )


@router.get("/{export_id}", response_model=ExportStatusResponse)
async def get_export_status(
    export_id: UUID,
    current_user: User = Depends(get_current_user),
    export_uc: ExportUseCase = Depends(container.application.export_use_case),
) -> ExportStatusResponse:
    """Get export status and download URL if ready."""
    export = await export_uc.get_export(export_id)
    if not export:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export not found",
        )

    # Verify ownership
    if export.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized",
        )

    return ExportStatusResponse(
        export_id=export.id,
        job_id=export.job_id,
        format=export.format,
        status=export.status.value,
        file_size_bytes=export.file_size_bytes,
        download_url=export.download_url,
        expires_at=export.expires_at.isoformat() if export.expires_at else None,
        created_at=export.created_at.isoformat(),
        completed_at=export.completed_at.isoformat() if export.completed_at else None,
    )


@router.get("/{export_id}/download")
async def download_export(
    export_id: UUID,
    current_user: User = Depends(get_current_user),
    export_uc: ExportUseCase = Depends(container.application.export_use_case),
):
    """Download export file (streaming)."""
    export = await export_uc.get_export(export_id)
    if not export:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export not found",
        )

    if export.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized",
        )

    if export.status.value != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Export not ready",
        )

    if not export.file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export file not found",
        )

    # Stream file from storage
    from geocare.infrastructure.storage.s3_client import S3StorageClient
    storage = container.infrastructure.file_storage

    async def file_iterator():
        async for chunk in storage.stream_file(export.file_path):
            yield chunk

    media_types = {
        "csv": "text/csv",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "parquet": "application/octet-stream",
    }

    return StreamingResponse(
        file_iterator(),
        media_type=media_types.get(export.format, "application/octet-stream"),
        headers={
            "Content-Disposition": f'attachment; filename="export_{export.job_id}.{export.format}"'
        },
    )


@router.get("", response_model=list[ExportStatusResponse])
async def list_exports(
    job_id: Optional[UUID] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    export_uc: ExportUseCase = Depends(container.application.export_use_case),
) -> list[ExportStatusResponse]:
    """List exports for current user."""
    exports = await export_uc.list_exports(
        user_id=current_user.id,
        job_id=job_id,
        limit=limit,
        offset=offset,
    )

    return [
        ExportStatusResponse(
            export_id=e.id,
            job_id=e.job_id,
            format=e.format,
            status=e.status.value,
            file_size_bytes=e.file_size_bytes,
            download_url=e.download_url,
            expires_at=e.expires_at.isoformat() if e.expires_at else None,
            created_at=e.created_at.isoformat(),
            completed_at=e.completed_at.isoformat() if e.completed_at else None,
        )
        for e in exports
    ]


@router.delete("/{export_id}")
async def delete_export(
    export_id: UUID,
    current_user: User = Depends(get_current_user),
    export_uc: ExportUseCase = Depends(container.application.export_use_case),
) -> dict:
    """Delete an export."""
    export = await export_uc.get_export(export_id)
    if not export:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export not found",
        )

    if export.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized",
        )

    await export_uc.delete_export(export_id)
    return {"message": "Export deleted"}