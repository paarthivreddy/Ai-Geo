"""Record and audit repository implementations."""

from typing import Optional, AsyncGenerator
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from geocare.domain.entities.record import PatientRecord, ReviewStatus, ConfidenceTier
from geocare.domain.entities.audit import AuditEntry, ProcessingMethod, DataSource
from geocare.domain.ports.repositories import RecordRepository, AuditRepository
from geocare.infrastructure.persistence.models import PatientRecordModel, AuditEntryModel


class RecordRepositoryImpl(RecordRepository):
    """SQLAlchemy implementation of RecordRepository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def bulk_create(self, records: list[PatientRecord]) -> list[PatientRecord]:
        models = [
            PatientRecordModel(
                id=str(r.id),
                job_id=str(r.job_id),
                row_index=r.row_index,
                patient_id_hash=r.patient_id_hash,
                original_address=r.original_address,
                normalized_address=r.normalized_address,
                parsed_address=r.parsed_address,
                enriched_address=r.enriched_address,
                confidence_score=r.confidence_score,
                confidence_tier=r.confidence_tier,
                match_method=r.match_method,
                review_status=r.review_status.value,
                reviewed_by=str(r.reviewed_by) if r.reviewed_by else None,
                reviewed_at=r.reviewed_at,
                review_notes=r.review_notes,
                geometry=r.geometry,
            )
            for r in records
        ]
        self.session.add_all(models)
        await self.session.flush()
        return records

    async def get_batch(
        self,
        job_id: UUID,
        offset: int,
        limit: int,
        review_status: Optional[str] = None,
        confidence_tier: Optional[str] = None,
    ) -> list[PatientRecord]:
        query = (
            select(PatientRecordModel)
            .where(PatientRecordModel.job_id == str(job_id))
            .order_by(PatientRecordModel.row_index)
            .limit(limit)
            .offset(offset)
        )
        if review_status:
            query = query.where(PatientRecordModel.review_status == review_status)
        if confidence_tier:
            query = query.where(PatientRecordModel.confidence_tier == confidence_tier)

        result = await self.session.execute(query)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def get_by_id(self, record_id: UUID) -> Optional[PatientRecord]:
        result = await self.session.execute(
            select(PatientRecordModel).where(PatientRecordModel.id == str(record_id))
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_entity(model)

    async def update(self, record: PatientRecord) -> PatientRecord:
        result = await self.session.execute(
            select(PatientRecordModel).where(PatientRecordModel.id == str(record.id))
        )
        model = result.scalar_one_or_none()
        if not model:
            raise ValueError(f"Record {record.id} not found")

        model.original_address = record.original_address
        model.normalized_address = record.normalized_address
        model.parsed_address = record.parsed_address
        model.enriched_address = record.enriched_address
        model.confidence_score = record.confidence_score
        model.confidence_tier = record.confidence_tier
        model.match_method = record.match_method
        model.review_status = record.review_status.value
        model.reviewed_by = str(record.reviewed_by) if record.reviewed_by else None
        model.reviewed_at = record.reviewed_at
        model.review_notes = record.review_notes
        model.geometry = record.geometry
        model.updated_at = record.updated_at

        await self.session.flush()
        return record

    async def bulk_update(self, records: list[PatientRecord]) -> list[PatientRecord]:
        for record in records:
            await self.update(record)
        return records

    async def count_by_status(self, job_id: UUID) -> dict[str, int]:
        result = await self.session.execute(
            select(PatientRecordModel.review_status, func.count(PatientRecordModel.id))
            .where(PatientRecordModel.job_id == str(job_id))
            .group_by(PatientRecordModel.review_status)
        )
        return dict(result.all())

    async def count_by_confidence(self, job_id: UUID) -> dict[str, int]:
        result = await self.session.execute(
            select(PatientRecordModel.confidence_tier, func.count(PatientRecordModel.id))
            .where(PatientRecordModel.job_id == str(job_id))
            .group_by(PatientRecordModel.confidence_tier)
        )
        return dict(result.all())

    async def stream_for_export(
        self,
        job_id: UUID,
        batch_size: int = 10000,
    ) -> AsyncGenerator[list[PatientRecord], None]:
        offset = 0
        while True:
            query = (
                select(PatientRecordModel)
                .where(PatientRecordModel.job_id == str(job_id))
                .order_by(PatientRecordModel.row_index)
                .limit(batch_size)
                .offset(offset)
            )
            result = await self.session.execute(query)
            records = [self._to_entity(m) for m in result.scalars().all()]
            if not records:
                break
            yield records
            offset += batch_size

    def _to_entity(self, model: PatientRecordModel) -> PatientRecord:
        return PatientRecord(
            id=UUID(model.id),
            job_id=UUID(model.job_id),
            row_index=model.row_index,
            patient_id_hash=model.patient_id_hash,
            original_address=model.original_address or {},
            normalized_address=model.normalized_address or {},
            parsed_address=model.parsed_address or {},
            enriched_address=model.enriched_address or {},
            confidence_score=model.confidence_score or {},
            confidence_tier=model.confidence_tier,
            match_method=model.match_method,
            review_status=ReviewStatus(model.review_status),
            reviewed_by=UUID(model.reviewed_by) if model.reviewed_by else None,
            reviewed_at=model.reviewed_at,
            review_notes=model.review_notes,
            geometry=model.geometry,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class AuditRepositoryImpl(AuditRepository):
    """SQLAlchemy implementation of AuditRepository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def bulk_create(self, entries: list[AuditEntry]) -> None:
        models = [
            AuditEntryModel(
                id=str(e.id),
                record_id=str(e.record_id),
                job_id=str(e.job_id),
                field_name=e.field_name,
                old_value=e.old_value,
                new_value=e.new_value,
                processing_method=e.processing_method.value,
                confidence=e.confidence,
                source_dataset=e.source_dataset.value,
                user_id=str(e.user_id) if e.user_id else None,
            )
            for e in entries
        ]
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
            result = await self.session.execute(
                select(AuditEntryModel)
                .where(AuditEntryModel.job_id == str(job_id))
                .order_by(AuditEntryModel.created_at)
                .limit(batch_size)
                .offset(offset)
            )
            entries = [self._to_entity(m) for m in result.scalars().all()]
            if not entries:
                break
            yield entries
            offset += batch_size

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