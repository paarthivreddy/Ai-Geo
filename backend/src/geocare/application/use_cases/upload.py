"""Upload use case for file handling and profiling."""

import polars as pl
import uuid
from typing import Optional, List, Dict, Any
from pathlib import Path
from uuid import UUID
from datetime import datetime

from geocare.domain.entities.job import ProcessingJob, JobStatus, ColumnMapping
from geocare.domain.ports.repositories import JobRepository, FileStoragePort
from geocare.application.use_cases.processing import ProcessUseCase
from geocare.domain.entities.user import User


class UploadResult:
    """Result of file upload and profiling."""

    def __init__(
        self,
        file_id: UUID,
        filename: str,
        size_bytes: int,
        row_count: int,
        column_count: int,
        columns: List[Dict[str, Any]],
        detected_address_columns: List[str],
    ):
        self.file_id = file_id
        self.filename = filename
        self.size_bytes = size_bytes
        self.row_count = row_count
        self.column_count = column_count
        self.columns = columns
        self.detected_address_columns = detected_address_columns


class ProfileResult:
    """Result of file profiling."""

    def __init__(
        self,
        file_id: UUID,
        filename: str,
        size_bytes: int,
        row_count: int,
        column_count: int,
        columns: List[Dict[str, Any]],
        detected_address_columns: List[str],
    ):
        self.file_id = file_id
        self.filename = filename
        self.size_bytes = size_bytes
        self.row_count = row_count
        self.column_count = column_count
        self.columns = columns
        self.detected_address_columns = detected_address_columns


class UploadUseCase:
    """Handle file upload, validation, profiling, and job creation."""

    ADDRESS_KEYWORDS = {
        "address", "addr", "line1", "line2", "street", "road", "lane",
        "locality", "area", "colony", "sector", "block", "plot", "house",
        "flat", "apartment", "apt", "building", "bldg", "floor", "flr",
        "landmark", "near", "opp", "behind", "beside", "next", "to",
        "pincode", "pin", "zip", "postal", "city", "town", "village",
        "district", "dist", "state", "st", "country", "nation",
    }

    def __init__(
        self,
        file_storage: FileStoragePort,
        job_repo: JobRepository,
        process_uc: ProcessUseCase,
    ):
        self.file_storage = file_storage
        self.job_repo = job_repo
        self.process_uc = process_uc

    async def process_upload(
        self,
        file_content: bytes,
        filename: str,
        content_type: str,
        user_id: UUID,
    ) -> UploadResult:
        """Process uploaded file: validate, store, profile, detect columns."""
        # Validate file
        self._validate_file(filename, content_type, len(file_content))

        # Generate file ID
        file_id = uuid.uuid4()

        # Store original file
        original_path = await self.file_storage.save_file(
            file_id, filename, file_content, "original"
        )

        # Convert to Parquet and profile
        profile = await self._profile_file(file_content, filename, content_type)

        # Save Parquet for processing
        parquet_path = await self._save_parquet(file_id, file_content, filename, content_type)

        # Store profile metadata
        await self.file_storage.save_metadata(file_id, {
            "filename": filename,
            "size_bytes": len(file_content),
            "row_count": profile.row_count,
            "column_count": profile.column_count,
            "columns": profile.columns,
            "detected_address_columns": profile.detected_address_columns,
            "original_path": original_path,
            "parquet_path": parquet_path,
            "content_type": content_type,
            "uploaded_at": datetime.utcnow().isoformat(),
            "user_id": str(user_id),
        })

        return UploadResult(
            file_id=file_id,
            filename=filename,
            size_bytes=len(file_content),
            row_count=profile.row_count,
            column_count=profile.column_count,
            columns=profile.columns,
            detected_address_columns=profile.detected_address_columns,
        )

    async def get_profile(self, file_id: UUID) -> Optional[ProfileResult]:
        """Get file profile by ID."""
        metadata = await self.file_storage.get_metadata(file_id)
        if not metadata:
            return None

        return ProfileResult(
            file_id=file_id,
            filename=metadata["filename"],
            size_bytes=metadata["size_bytes"],
            row_count=metadata["row_count"],
            column_count=metadata["column_count"],
            columns=metadata["columns"],
            detected_address_columns=metadata["detected_address_columns"],
        )

    async def create_job(
        self,
        file_id: UUID,
        column_mapping: Dict[str, Optional[str]],
        chunk_size: int,
        user_id: UUID,
    ) -> ProcessingJob:
        """Create processing job from profiled file."""
        metadata = await self.file_storage.get_metadata(file_id)
        if not metadata:
            raise ValueError("File not found")

        # Create column mapping
        mapping = ColumnMapping.from_dict(column_mapping)

        # Create job
        job = ProcessingJob(
            user_id=user_id,
            filename=metadata["filename"],
            original_file_path=metadata["original_path"],
            parquet_file_path=metadata["parquet_path"],
            total_rows=metadata["row_count"],
            total_columns=metadata["column_count"],
            column_mapping=mapping,
            detected_address_columns=metadata["detected_address_columns"],
            chunk_size=chunk_size,
        )

        # Save job
        job = await self.job_repo.create(job)

        # Chunk the file
        await self._chunk_file(job, chunk_size)

        return job

    async def _profile_file(
        self,
        file_content: bytes,
        filename: str,
        content_type: str,
    ) -> ProfileResult:
        """Profile file using Polars."""
        # Load with Polars
        if content_type == "text/csv":
            df = pl.read_csv(
                file_content,
                infer_schema_length=10000,
                try_parse_dates=False,
            )
        elif content_type in (
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ):
            df = pl.read_excel(file_content, infer_schema_length=10000)
        else:
            raise ValueError(f"Unsupported content type: {content_type}")

        # Get column stats
        columns = []
        for col in df.columns:
            series = df[col]
            null_count = series.null_count()
            total = len(series)
            distinct = series.n_unique()

            # Sample values
            sample = series.drop_nulls().head(5).to_list()

            # Min/max length (null when series entirely null — coerce to 0)
            str_series = series.cast(pl.Utf8)
            lengths = str_series.str.len_chars()
            min_len = lengths.min() or 0
            max_len = lengths.max() or 0

            # Pattern regex (simplified)
            pattern = self._infer_pattern(sample)

            columns.append({
                "name": col,
                "dtype": str(series.dtype),
                "null_pct": round(null_count / total * 100, 2) if total > 0 else 0,
                "distinct_count": distinct,
                "sample_values": sample,
                "min_length": min_len,
                "max_length": max_len,
                "pattern_regex": pattern,
            })

        # Detect address columns
        detected = self._detect_address_columns(columns, df)

        return ProfileResult(
            file_id=uuid.uuid4(),  # placeholder
            filename=filename,
            size_bytes=len(file_content),
            row_count=len(df),
            column_count=len(df.columns),
            columns=columns,
            detected_address_columns=detected,
        )

    def _detect_address_columns(
        self,
        columns: List[Dict],
        df: pl.DataFrame,
    ) -> List[str]:
        """Detect columns that likely contain address data."""
        detected = []

        for col_info in columns:
            col_name = col_info["name"].lower()

            # Check column name
            name_score = sum(
                1 for kw in self.ADDRESS_KEYWORDS if kw in col_name
            )

            # Check content (sample)
            col_data = df[col_info["name"]].drop_nulls().head(20)
            content_score = 0

            for val in col_data:
                val_str = str(val).lower()
                # Check for PIN code pattern
                if any(kw in val_str for kw in ["pincode", "pin", "zip", "postal"]):
                    content_score += 2
                # Check for common Indian locality suffixes
                if any(val_str.endswith(suf) for suf in ["nagar", "colony", "sector", "extension", "layout", "vihar", "pura", "ganj"]):
                    content_score += 1
                # Check for 6-digit number (PIN)
                import re
                if re.search(r'\b[1-8]\d{5}\b', val_str):
                    content_score += 2

            if name_score >= 2 or content_score >= 2:
                detected.append(col_info["name"])

        return detected

    def _infer_pattern(self, sample: List) -> str:
        """Infer regex pattern from sample values."""
        if not sample:
            return ""
        # Simplified - just check if all values match a pattern
        # Could be enhanced with regex inference
        return ""

    def _validate_file(self, filename: str, content_type: str, size: int):
        """Validate uploaded file."""
        allowed_types = {
            "text/csv",
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }
        if content_type not in allowed_types:
            raise ValueError(f"Unsupported file type: {content_type}")

        allowed_ext = {".csv", ".xls", ".xlsx"}
        ext = Path(filename).suffix.lower()
        if ext not in allowed_ext:
            raise ValueError(f"Unsupported file extension: {ext}")

        max_size = 2 * 1024 * 1024 * 1024  # 2GB
        if size > max_size:
            raise ValueError(f"File too large: {size} bytes (max {max_size})")

    async def _save_parquet(
        self,
        file_id: UUID,
        file_content: bytes,
        filename: str,
        content_type: str,
    ) -> str:
        """Save file as Parquet for processing."""
        if content_type == "text/csv":
            df = pl.read_csv(file_content, infer_schema_length=10000)
        else:
            df = pl.read_excel(file_content, infer_schema_length=10000)

        from geocare.config.settings import settings
        import tempfile
        base = Path(settings.UPLOAD_DIR)
        try:
            base.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError):
            base = Path(tempfile.gettempdir()) / "geocare-uploads"
            base.mkdir(parents=True, exist_ok=True)

        parquet_path = base / "chunks" / str(file_id) / "data.parquet"
        parquet_path.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(str(parquet_path))

        return str(parquet_path)

    async def _chunk_file(self, job: ProcessingJob, chunk_size: int):
        """Split Parquet file into chunks for parallel processing."""
        df = pl.read_parquet(job.parquet_file_path)
        total_rows = len(df)

        job.total_chunks = (total_rows + chunk_size - 1) // chunk_size

        for i in range(job.total_chunks):
            start = i * chunk_size
            end = min(start + chunk_size, total_rows)
            chunk_df = df.slice(start, end - start)

            parquet_base = Path(job.parquet_file_path).parent.parent  # {base}/chunks/{file_id}
            chunk_path = parquet_base / str(job.id) / f"chunk_{i:05d}.parquet"
            chunk_path.parent.mkdir(parents=True, exist_ok=True)
            chunk_df.write_parquet(str(chunk_path))

            # Save chunk metadata
            from geocare.domain.entities.job import JobChunk, ChunkStatus
            chunk = JobChunk(
                job_id=job.id,
                chunk_index=i,
                storage_path=str(chunk_path),
                row_count=len(chunk_df),
                status=ChunkStatus.PENDING,
            )
            # Would save to chunk repository

        await self.job_repo.update(job)