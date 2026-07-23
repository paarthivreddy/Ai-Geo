"""Audit use case for trail queries and exports."""

from typing import Optional, List, AsyncGenerator
from uuid import UUID
from datetime import datetime

from geocare.domain.entities.audit import AuditEntry, ProcessingMethod, DataSource
from geocare.domain.value_objects.audit import AuditSummary
from geocare.domain.ports.repositories import AuditRepository


class AuditUseCase:
    """Query and export audit trails."""

    def __init__(self, audit_repo: AuditRepository):
        self.audit_repo = audit_repo

    async def get_record_audit(self, record_id: UUID) -> List[AuditEntry]:
        """Get full audit trail for a single record."""
        return await self.audit_repo.get_for_record(record_id)

    async def get_job_audit_summary(self, job_id: UUID) -> AuditSummary:
        """Get aggregated audit statistics for a job."""
        entries = await self.audit_repo.get_for_job(job_id, limit=100000)

        if not entries:
            return AuditSummary()

        from collections import Counter

        by_method = Counter(e.processing_method.value for e in entries)
        by_field = Counter(e.field_name for e in entries)
        avg_confidence = sum(e.confidence for e in entries) / len(entries)
        user_overrides = sum(1 for e in entries if e.user_id is not None)

        return AuditSummary(
            total_changes=len(entries),
            by_method=dict(by_method),
            by_field=dict(by_field),
            avg_confidence=round(avg_confidence, 2),
            user_overrides=user_overrides,
        )

    async def get_job_audit_entries(
        self,
        job_id: UUID,
        limit: int = 10000,
        offset: int = 0,
    ) -> List[AuditEntry]:
        """Get paginated audit entries for a job."""
        return await self.audit_repo.get_for_job(job_id, limit, offset)

    async def stream_audit_for_job(
        self,
        job_id: UUID,
        batch_size: int = 10000,
    ) -> AsyncGenerator[List[AuditEntry], None]:
        """Stream audit entries for export."""
        async for batch in self.audit_repo.stream_for_job(job_id, batch_size):
            yield batch

    async def export_audit_trail(
        self,
        job_id: UUID,
        format: str = "csv",
    ) -> bytes:
        """Export complete audit trail for a job."""
        if format == "csv":
            import csv
            import io

            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow([
                "id", "record_id", "job_id", "field_name",
                "old_value", "new_value", "processing_method",
                "confidence", "source_dataset", "user_id", "timestamp",
            ])

            async for batch in self.audit_repo.stream_for_job(job_id):
                for entry in batch:
                    writer.writerow([
                        str(entry.id),
                        str(entry.record_id),
                        str(entry.job_id),
                        entry.field_name,
                        entry.old_value or "",
                        entry.new_value or "",
                        entry.processing_method.value,
                        entry.confidence,
                        entry.source_dataset.value,
                        str(entry.user_id) if entry.user_id else "",
                        entry.created_at.isoformat(),
                    ])

            return output.getvalue().encode()

        elif format == "parquet":
            import polars as pl

            rows = []
            async for batch in self.audit_repo.stream_for_job(job_id):
                for entry in batch:
                    rows.append({
                        "id": str(entry.id),
                        "record_id": str(entry.record_id),
                        "job_id": str(entry.job_id),
                        "field_name": entry.field_name,
                        "old_value": entry.old_value,
                        "new_value": entry.new_value,
                        "processing_method": entry.processing_method.value,
                        "confidence": entry.confidence,
                        "source_dataset": entry.source_dataset.value,
                        "user_id": str(entry.user_id) if entry.user_id else None,
                        "timestamp": entry.created_at,
                    })

            df = pl.DataFrame(rows)
            import io
            buf = io.BytesIO()
            df.write_parquet(buf)
            return buf.getvalue()

        else:
            raise ValueError(f"Unsupported format: {format}")