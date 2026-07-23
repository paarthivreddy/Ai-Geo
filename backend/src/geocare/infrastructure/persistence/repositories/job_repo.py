"""Job repository implementation."""

from typing import Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from geocare.domain.entities.job import ProcessingJob, JobStatus, JobChunk, JobQualityStats
from geocare.domain.ports.repositories import JobRepository, ChunkRepository
from geocare.infrastructure.persistence.models import (
    ProcessingJobModel,
    JobChunkModel,
    JobQualityStatsModel,
)


class JobRepositoryImpl(JobRepository):
    """SQLAlchemy implementation of JobRepository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, job: ProcessingJob) -> ProcessingJob:
        model = ProcessingJobModel(
            id=str(job.id),
            user_id=str(job.user_id),
            filename=job.filename,
            original_file_path=job.original_file_path,
            parquet_file_path=job.parquet_file_path,
            total_rows=job.total_rows,
            total_columns=job.total_columns,
            column_mapping=job.column_mapping.to_dict() if hasattr(job.column_mapping, 'to_dict') else job.column_mapping,
            detected_address_columns=job.detected_address_columns,
            status=job.status.value,
            progress_pct=job.progress_pct,
            processed_rows=job.processed_rows,
            succeeded_rows=job.succeeded_rows,
            failed_rows=job.failed_rows,
            manual_review_rows=job.manual_review_rows,
            chunk_size=job.chunk_size,
            total_chunks=job.total_chunks,
            completed_chunks=job.completed_chunks,
            failed_chunks=job.failed_chunks,
            error_message=job.error_message,
            started_at=job.started_at,
            completed_at=job.completed_at,
        )
        self.session.add(model)
        await self.session.flush()
        return job

    async def get(self, job_id: UUID) -> Optional[ProcessingJob]:
        result = await self.session.execute(
            select(ProcessingJobModel).where(ProcessingJobModel.id == str(job_id))
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_entity(model)

    async def get_by_user(
        self,
        user_id: UUID,
        limit: int = 20,
        offset: int = 0,
        status: Optional[str] = None,
    ) -> list[ProcessingJob]:
        query = (
            select(ProcessingJobModel)
            .where(ProcessingJobModel.user_id == str(user_id))
            .order_by(ProcessingJobModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if status:
            query = query.where(ProcessingJobModel.status == status)
        result = await self.session.execute(query)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def update(self, job: ProcessingJob) -> ProcessingJob:
        result = await self.session.execute(
            select(ProcessingJobModel).where(ProcessingJobModel.id == str(job.id))
        )
        model = result.scalar_one_or_none()
        if not model:
            raise ValueError(f"Job {job.id} not found")

        model.filename = job.filename
        model.original_file_path = job.original_file_path
        model.parquet_file_path = job.parquet_file_path
        model.total_rows = job.total_rows
        model.total_columns = job.total_columns
        model.column_mapping = job.column_mapping.to_dict() if hasattr(job.column_mapping, 'to_dict') else job.column_mapping
        model.detected_address_columns = job.detected_address_columns
        model.status = job.status.value
        model.progress_pct = job.progress_pct
        model.processed_rows = job.processed_rows
        model.succeeded_rows = job.succeeded_rows
        model.failed_rows = job.failed_rows
        model.manual_review_rows = job.manual_review_rows
        model.chunk_size = job.chunk_size
        model.total_chunks = job.total_chunks
        model.completed_chunks = job.completed_chunks
        model.failed_chunks = job.failed_chunks
        model.error_message = job.error_message
        model.started_at = job.started_at
        model.completed_at = job.completed_at
        model.updated_at = job.updated_at

        await self.session.flush()
        return job

    async def delete(self, job_id: UUID) -> bool:
        result = await self.session.execute(
            select(ProcessingJobModel).where(ProcessingJobModel.id == str(job_id))
        )
        model = result.scalar_one_or_none()
        if not model:
            return False
        await self.session.delete(model)
        await self.session.flush()
        return True

    async def count_by_user(self, user_id: UUID) -> int:
        result = await self.session.execute(
            select(func.count(ProcessingJobModel.id)).where(
                ProcessingJobModel.user_id == str(user_id)
            )
        )
        return result.scalar_one()

    def _to_entity(self, model: ProcessingJobModel) -> ProcessingJob:
        from geocare.domain.entities.job import ColumnMapping
        return ProcessingJob(
            id=UUID(model.id),
            user_id=UUID(model.user_id),
            filename=model.filename,
            original_file_path=model.original_file_path,
            parquet_file_path=model.parquet_file_path,
            total_rows=model.total_rows,
            total_columns=model.total_columns,
            column_mapping=ColumnMapping.from_dict(model.column_mapping),
            detected_address_columns=model.detected_address_columns or [],
            status=JobStatus(model.status),
            progress_pct=model.progress_pct,
            processed_rows=model.processed_rows,
            succeeded_rows=model.succeeded_rows,
            failed_rows=model.failed_rows,
            manual_review_rows=model.manual_review_rows,
            chunk_size=model.chunk_size,
            total_chunks=model.total_chunks,
            completed_chunks=model.completed_chunks or [],
            failed_chunks=model.failed_chunks or [],
            error_message=model.error_message,
            started_at=model.started_at,
            completed_at=model.completed_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class ChunkRepositoryImpl(ChunkRepository):
    """SQLAlchemy implementation of ChunkRepository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_batch(self, chunks: list[JobChunk]) -> list[JobChunk]:
        models = [
            JobChunkModel(
                id=str(c.id),
                job_id=str(c.job_id),
                chunk_index=c.chunk_index,
                storage_path=c.storage_path,
                row_count=c.row_count,
                status=c.status.value,
                retry_count=c.retry_count,
                max_retries=c.max_retries,
                error_message=c.error_message,
                worker_id=c.worker_id,
                started_at=c.started_at,
                completed_at=c.completed_at,
            )
            for c in chunks
        ]
        self.session.add_all(models)
        await self.session.flush()
        return chunks

    async def get_pending(self, job_id: UUID) -> list[JobChunk]:
        result = await self.session.execute(
            select(JobChunkModel)
            .where(
                JobChunkModel.job_id == str(job_id),
                JobChunkModel.status == "pending",
            )
            .order_by(JobChunkModel.chunk_index)
        )
        return [self._to_entity(m) for m in result.scalars().all()]

    async def get_by_index(self, job_id: UUID, chunk_index: int) -> Optional[JobChunk]:
        result = await self.session.execute(
            select(JobChunkModel).where(
                JobChunkModel.job_id == str(job_id),
                JobChunkModel.chunk_index == chunk_index,
            )
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_entity(model)

    async def update(self, chunk: JobChunk) -> JobChunk:
        result = await self.session.execute(
            select(JobChunkModel).where(
                JobChunkModel.job_id == str(chunk.job_id),
                JobChunkModel.chunk_index == chunk.chunk_index,
            )
        )
        model = result.scalar_one_or_none()
        if not model:
            raise ValueError(f"Chunk {chunk.chunk_index} for job {chunk.job_id} not found")

        model.status = chunk.status.value
        model.retry_count = chunk.retry_count
        model.error_message = chunk.error_message
        model.worker_id = chunk.worker_id
        model.started_at = chunk.started_at
        model.completed_at = chunk.completed_at

        await self.session.flush()
        return chunk

    async def count_by_status(self, job_id: UUID) -> dict[str, int]:
        from collections import Counter
        result = await self.session.execute(
            select(JobChunkModel.status, func.count(JobChunkModel.id))
            .where(JobChunkModel.job_id == str(job_id))
            .group_by(JobChunkModel.status)
        )
        return dict(result.all())

    def _to_entity(self, model: JobChunkModel) -> JobChunk:
        from geocare.domain.entities.job import ChunkStatus
        return JobChunk(
            id=UUID(model.id),
            job_id=UUID(model.job_id),
            chunk_index=model.chunk_index,
            storage_path=model.storage_path,
            row_count=model.row_count,
            status=ChunkStatus(model.status),
            retry_count=model.retry_count,
            max_retries=model.max_retries,
            error_message=model.error_message,
            worker_id=model.worker_id,
            started_at=model.started_at,
            completed_at=model.completed_at,
            created_at=model.created_at,
        )


class JobQualityStatsRepository:
    """Repository for job quality statistics."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, stats: JobQualityStats) -> JobQualityStats:
        model = JobQualityStatsModel(
            job_id=str(stats.job_id),
            total_records=stats.total_records,
            complete_addresses_before=stats.complete_addresses_before,
            missing_pincode_before=stats.missing_pincode_before,
            missing_locality_before=stats.missing_locality_before,
            missing_city_before=stats.missing_city_before,
            missing_district_before=stats.missing_district_before,
            missing_state_before=stats.missing_state_before,
            invalid_addresses_before=stats.invalid_addresses_before,
            duplicate_addresses_before=stats.duplicate_addresses_before,
            overall_quality_before=stats.overall_quality_before,
            pincodes_added=stats.pincodes_added,
            cities_added=stats.cities_added,
            districts_added=stats.districts_added,
            states_added=stats.states_added,
            spell_corrections=stats.spell_corrections,
            improved_records=stats.improved_records,
            manual_review_records=stats.manual_review_records,
            final_quality_score=stats.final_quality_score,
            improvement_percentage=stats.improvement_percentage,
            confidence_high=stats.confidence_high,
            confidence_medium=stats.confidence_medium,
            confidence_low=stats.confidence_low,
            confidence_unverified=stats.confidence_unverified,
            profiling_time=stats.profiling_time,
            processing_time=stats.processing_time,
            reporting_time=stats.reporting_time,
            export_time=stats.export_time,
        )
        self.session.add(model)
        await self.session.flush()
        return stats

    async def get(self, job_id: UUID) -> Optional[JobQualityStats]:
        result = await self.session.execute(
            select(JobQualityStatsModel).where(JobQualityStatsModel.job_id == str(job_id))
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_entity(model)

    def _to_entity(self, model: JobQualityStatsModel) -> JobQualityStats:
        return JobQualityStats(
            job_id=UUID(model.job_id),
            total_records=model.total_records,
            complete_addresses_before=model.complete_addresses_before,
            missing_pincode_before=model.missing_pincode_before,
            missing_locality_before=model.missing_locality_before,
            missing_city_before=model.missing_city_before,
            missing_district_before=model.missing_district_before,
            missing_state_before=model.missing_state_before,
            invalid_addresses_before=model.invalid_addresses_before,
            duplicate_addresses_before=model.duplicate_addresses_before,
            overall_quality_before=model.overall_quality_before,
            pincodes_added=model.pincodes_added,
            cities_added=model.cities_added,
            districts_added=model.districts_added,
            states_added=model.states_added,
            spell_corrections=model.spell_corrections,
            improved_records=model.improved_records,
            manual_review_records=model.manual_review_records,
            final_quality_score=model.final_quality_score,
            improvement_percentage=model.improvement_percentage,
            confidence_high=model.confidence_high,
            confidence_medium=model.confidence_medium,
            confidence_low=model.confidence_low,
            confidence_unverified=model.confidence_unverified,
            profiling_time=model.profiling_time,
            processing_time=model.processing_time,
            reporting_time=model.reporting_time,
            export_time=model.export_time,
            created_at=model.created_at,
        )