"""File upload and profiling API routes."""

import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from geocare.config.container import container
from geocare.application.use_cases.upload import UploadUseCase
from geocare.domain.ports.repositories import FileStoragePort
from geocare.infrastructure.storage import LocalStorageClient
from geocare.presentation.api.deps import get_current_user
from geocare.domain.entities.user import User

router = APIRouter(prefix="/files", tags=["Files"])


# Request/Response Models
class ColumnInfo(BaseModel):
    name: str
    dtype: str
    null_pct: float
    distinct_count: int
    sample_values: list[str]
    min_length: int
    max_length: int
    pattern_regex: Optional[str] = None


class FileUploadResponse(BaseModel):
    file_id: UUID
    filename: str
    size_bytes: int
    row_count: int
    column_count: int
    columns: list[ColumnInfo]
    detected_address_columns: list[str]


class ColumnMappingRequest(BaseModel):
    patient_id: Optional[str] = None
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    landmark: Optional[str] = None
    pincode: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None


class ColumnMappingResponse(BaseModel):
    job_id: UUID
    message: str


# Routes
@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    upload_uc: UploadUseCase = Depends(container.application.upload_use_case),
) -> FileUploadResponse:
    """Upload CSV/Excel file for processing."""
    # Validate file type
    allowed_types = {
        "text/csv",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file.content_type}. Allowed: CSV, XLS, XLSX",
        )

    # Validate file size
    max_size = container.config.max_file_size_bytes()
    file_content = await file.read()
    if len(file_content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size: {container.config.MAX_FILE_SIZE_MB} MB",
        )

    # Process upload
    result = await upload_uc.process_upload(
        file_content=file_content,
        filename=file.filename,
        content_type=file.content_type,
        user_id=current_user.id,
    )

    return FileUploadResponse(
        file_id=result.file_id,
        filename=result.filename,
        size_bytes=result.size_bytes,
        row_count=result.row_count,
        column_count=result.column_count,
        columns=[ColumnInfo(**c) for c in result.columns],
        detected_address_columns=result.detected_address_columns,
    )


@router.get("/{file_id}/profile", response_model=FileUploadResponse)
async def get_file_profile(
    file_id: UUID,
    current_user: User = Depends(get_current_user),
    upload_uc: UploadUseCase = Depends(container.application.upload_use_case),
) -> FileUploadResponse:
    """Get file profile with column statistics and detected address columns."""
    result = await upload_uc.get_profile(file_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    return FileUploadResponse(
        file_id=result.file_id,
        filename=result.filename,
        size_bytes=result.size_bytes,
        row_count=result.row_count,
        column_count=result.column_count,
        columns=[ColumnInfo(**c) for c in result.columns],
        detected_address_columns=result.detected_address_columns,
    )


@router.post("/{file_id}/confirm-columns", response_model=ColumnMappingResponse)
async def confirm_columns(
    file_id: UUID,
    mapping: ColumnMappingRequest,
    chunk_size: int = 50000,
    current_user: User = Depends(get_current_user),
    upload_uc: UploadUseCase = Depends(container.application.upload_use_case),
) -> ColumnMappingResponse:
    """Confirm column mapping and create processing job."""
    job = await upload_uc.create_job(
        file_id=file_id,
        column_mapping=mapping.model_dump(exclude_none=True),
        chunk_size=chunk_size,
        user_id=current_user.id,
    )

    return ColumnMappingResponse(
        job_id=job.id,
        message=f"Job created with {job.total_chunks} chunks. Processing started.",
    )


@router.delete("/{file_id}")
async def delete_file(
    file_id: UUID,
    current_user: User = Depends(get_current_user),
    file_storage: LocalStorageClient = Depends(container.infrastructure.file_storage),
) -> dict:
    """Delete uploaded file and associated data."""
    await file_storage.delete_file(file_id)
    return {"message": "File deleted successfully"}