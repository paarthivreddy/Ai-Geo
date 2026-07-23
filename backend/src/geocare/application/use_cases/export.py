"""Export use case for downloading enriched data."""

from typing import Optional, List, AsyncGenerator
from uuid import UUID
from datetime import datetime

from geocare.domain.ports.repositories import RecordRepository, JobRepository
from geocare.infrastructure.storage import FileStoragePort


class ExportUseCase:
    """Generate and manage data exports."""

    def __init__(
        self,
        job_repo: JobRepository,
        record_repo: RecordRepository,
        storage: FileStoragePort,
    ):
        self.job_repo = job_repo
        self.record_repo = record_repo
        self.storage = storage

    async def create_export(
        self,
        job_id: UUID,
        format: str = "csv",
        confidence_tiers: Optional[List[str]] = None,
        include_audit: bool = False,
        include_original: bool = True,
        user_id: UUID = None,
    ) -> str:
        """Create an export job and return export ID."""
        from uuid import uuid4

        job = await self.job_repo.get(job_id)
        if not job:
            raise ValueError("Job not found")

        if job.status.value != "completed":
            raise ValueError("Job must be completed before export")

        export_id = uuid4()

        # Save export metadata
        await self.storage.save_metadata(f"export_{export_id}", {
            "export_id": str(export_id),
            "job_id": str(job_id),
            "format": format,
            "confidence_tiers": confidence_tiers,
            "include_audit": include_audit,
            "include_original": include_original,
            "user_id": str(user_id) if user_id else None,
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
        })

        # Start export in background (would enqueue task)
        # await self.queue.enqueue("generate_export", export_id=str(export_id), ...)

        return str(export_id)

    async def generate_export(
        self,
        export_id: UUID,
        job_id: UUID,
        format: str,
        confidence_tiers: Optional[List[str]] = None,
        include_audit: bool = False,
        include_original: bool = True,
    ) -> str:
        """Generate export file and save to storage."""
        # Stream records
        output_path = f"exports/{export_id}.{format}"

        if format == "csv":
            await self._generate_csv(export_id, job_id, output_path, confidence_tiers, include_original)
        elif format == "xlsx":
            await self._generate_xlsx(export_id, job_id, output_path, confidence_tiers, include_original)
        elif format == "parquet":
            await self._generate_parquet(export_id, job_id, output_path, confidence_tiers, include_original)
        else:
            raise ValueError(f"Unsupported format: {format}")

        return output_path

    async def _generate_csv(
        self,
        export_id: UUID,
        job_id: UUID,
        output_path: str,
        confidence_tiers: Optional[List[str]],
        include_original: bool,
    ):
        """Generate CSV export streaming records."""
        import csv
        import io

        # Build header
        header = [
            "record_id", "row_index", "patient_id_hash",
            "enriched_line1", "enriched_line2", "enriched_locality",
            "enriched_city", "enriched_district", "enriched_state",
            "enriched_pincode", "enriched_country",
            "confidence_overall", "confidence_tier", "match_method",
            "review_status",
        ]

        if include_original:
            header += [
                "original_line1", "original_line2", "original_landmark",
                "original_pincode", "original_city", "original_district",
                "original_state", "original_country",
            ]

        # Stream records and write
        async with self.storage.open_write(output_path) as f:
            writer = csv.writer(f)
            writer.writerow(header)

            async for batch in self.record_repo.stream_for_export(job_id):
                for record in batch:
                    # Filter by confidence tier
                    if confidence_tiers and record.confidence_score.get("tier") not in confidence_tiers:
                        continue

                    enriched = record.enriched_address or {}
                    original = record.original_address or {}
                    confidence = record.confidence_score or {}

                    row = [
                        str(record.id),
                        record.row_index,
                        record.patient_id_hash,
                        enriched.get("line1", ""),
                        enriched.get("line2", ""),
                        enriched.get("locality", ""),
                        enriched.get("city", ""),
                        enriched.get("district", ""),
                        enriched.get("state", ""),
                        enriched.get("pincode", ""),
                        enriched.get("country", ""),
                        confidence.get("overall", 0),
                        confidence.get("tier", "unverified"),
                        confidence.get("method", "manual"),
                        record.review_status.value if hasattr(record.review_status, 'value') else record.review_status,
                    ]

                    if include_original:
                        row += [
                            original.get("line1", ""),
                            original.get("line2", ""),
                            original.get("landmark", ""),
                            original.get("pincode", ""),
                            original.get("city", ""),
                            original.get("district", ""),
                            original.get("state", ""),
                            original.get("country", ""),
                        ]

                    writer.writerow(row)

        # Update export status
        file_size = await self.storage.get_size(output_path)
        await self.storage.save_metadata(f"export_{export_id}", {
            "status": "completed",
            "file_path": output_path,
            "file_size": file_size,
            "completed_at": datetime.utcnow().isoformat(),
        })

    async def _generate_parquet(
        self,
        export_id: UUID,
        job_id: UUID,
        output_path: str,
        confidence_tiers: Optional[List[str]],
        include_original: bool,
    ):
        """Generate Parquet export using Polars."""
        import polars as pl

        rows = []

        async for batch in self.record_repo.stream_for_export(job_id):
            for record in batch:
                if confidence_tiers and record.confidence_score.get("tier") not in confidence_tiers:
                    continue

                enriched = record.enriched_address or {}
                original = record.original_address or {}
                confidence = record.confidence_score or {}

                row = {
                    "record_id": str(record.id),
                    "row_index": record.row_index,
                    "patient_id_hash": record.patient_id_hash,
                    "enriched_line1": enriched.get("line1", ""),
                    "enriched_line2": enriched.get("line2", ""),
                    "enriched_locality": enriched.get("locality", ""),
                    "enriched_city": enriched.get("city", ""),
                    "enriched_district": enriched.get("district", ""),
                    "enriched_state": enriched.get("state", ""),
                    "enriched_pincode": enriched.get("pincode", ""),
                    "enriched_country": enriched.get("country", ""),
                    "confidence_overall": confidence.get("overall", 0),
                    "confidence_tier": confidence.get("tier", "unverified"),
                    "match_method": confidence.get("method", "manual"),
                    "review_status": record.review_status.value if hasattr(record.review_status, 'value') else record.review_status,
                }

                if include_original:
                    row.update({
                        "original_line1": original.get("line1", ""),
                        "original_line2": original.get("line2", ""),
                        "original_landmark": original.get("landmark", ""),
                        "original_pincode": original.get("pincode", ""),
                        "original_city": original.get("city", ""),
                        "original_district": original.get("district", ""),
                        "original_state": original.get("state", ""),
                        "original_country": original.get("country", ""),
                    })

                rows.append(row)

        # Write Parquet
        df = pl.DataFrame(rows)
        df.write_parquet(output_path)

        # Update metadata
        file_size = await self.storage.get_size(output_path)
        await self.storage.save_metadata(f"export_{export_id}", {
            "status": "completed",
            "file_path": output_path,
            "file_size": file_size,
            "completed_at": datetime.utcnow().isoformat(),
        })

    async def _generate_xlsx(
        self,
        export_id: UUID,
        job_id: UUID,
        output_path: str,
        confidence_tiers: Optional[List[str]],
        include_original: bool,
    ):
        """Generate Excel export."""
        # Similar to CSV but using openpyxl
        # For brevity, delegate to CSV then convert or use openpyxl directly
        pass

    async def get_export_status(self, export_id: UUID) -> dict:
        """Get export status and download URL if ready."""
        metadata = await self.storage.get_metadata(f"export_{export_id}")
        if not metadata:
            raise ValueError("Export not found")

        return metadata

    async def download_export(self, export_id: UUID) -> AsyncGenerator[bytes, None]:
        """Stream export file for download."""
        metadata = await self.storage.get_metadata(f"export_{export_id}")
        if not metadata or metadata.get("status") != "completed":
            raise ValueError("Export not ready")

        async for chunk in self.storage.stream_file(metadata["file_path"]):
            yield chunk