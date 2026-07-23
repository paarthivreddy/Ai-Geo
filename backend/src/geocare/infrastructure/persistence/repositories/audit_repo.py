"""Audit repository implementation."""

from typing import AsyncGenerator, Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from geocare.domain.entities.audit import AuditEntry, ProcessingMethod, DataSource
from geocare.domain.ports.repositories import AuditRepository
from geocare.infrastructure.persistence.models import AuditEntryModel


class AuditRepositoryImpl(AuditRepository):
    """SQLAlchemy implementation of AuditRepository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def bulk_create(self, entries: list[AuditEntry]) -> None:
        models = [self._to_model(e) for e in entries]
        self.session.add_all(models)
        await self.session.flush()

    async def get_for_record(self, record_id: UUID) -> list[AuditEntry]:
        result = await self.session.execute(
            select(AuditEntryModel)
            .where(AuditEntryModel.record_id == str(record_id))
            .order_by(AuditEntryModel.created_at)
        )
        return [self._to_entity(m) for m in result.scalars().all()]

    async def get_for_job(
        self,
        job_id: UUID,
        limit: int = 10000,
        offset: int = 0,
    ) -> list[AuditEntry]:
        result = await self.session.execute(
            select(AuditEntryModel)
            .where(AuditEntryModel.job_id == str(job_id))
            .order_by(AuditEntryModel.created_at)
            .limit(limit)
            .offset(offset)
        )
        return [self._to_entity(m) for m in result.scalars().all()]

    async def stream_for_job(
        self,
        job_id: UUID,
        batch_size: int = 10000,
    ) -> AsyncGenerator[list[AuditEntry], None]:
        offset = 0
        while True:
            batch = await self.get_for_job(job_id, batch_size, offset)
            if not batch:
                break
            yield batch
            offset += batch_size

    def _to_model(self, entry: AuditEntry) -> AuditEntryModel:
        return AuditEntryModel(
            id=str(entry.id),
            record_id=str(entry.record_id),
            job_id=str(entry.job_id),
            field_name=entry.field_name,
            old_value=entry.old_value,
            new_value=entry.new_value,
            processing_method=entry.processing_method.value,
            confidence=entry.confidence,
            source_dataset=entry.source_dataset.value,
            user_id=str(entry.user_id) if entry.user_id else None,
            created_at=entry.created_at,
        )

    def _to_entity(self, model: AuditEntryModel) -> AuditEntry:
        return AuditEntry(
            id=UUID(model.id),
            record_id=UUID(model.record_id),
            job_id=UUID(model.job_id),
            field_name=model.field_name,
            old_value=model.old_value,
            new_value=model.new_value,
            processing_method=ProcessingMethod(model.processing_method),
            confidence=model.confidence,
            source_dataset=DataSource(model.source_dataset),
            user_id=UUID(model.user_id) if model.user_id else None,
            created_at=model.created_at,
        )