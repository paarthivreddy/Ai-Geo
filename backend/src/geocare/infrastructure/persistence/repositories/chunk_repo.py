"""Chunk repository implementation."""

from typing import Optional, List
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from geocare.domain.entities.job import JobChunk, ChunkStatus
from geocare.domain.ports.repositories import ChunkRepository
from geocare.infrastructure.persistence.models import JobChunkModel


class ChunkRepositoryImpl(ChunkRepository):
    """SQLAlchemy implementation of ChunkRepository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_batch(self, chunks: List[JobChunk]) -> List[JobChunk]:
        """Create multiple chunks."""
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

    async def get_pending(self, job_id: UUID) -> List[JobChunk]:
        """Get pending chunks for a job."""
        result = await self.session.execute(
            select(JobChunkModel)
            .where(
                JobChunkModel.job_id == str(job_id),
                JobChunkModel.status == ChunkStatus.PENDING.value,
            )
            .order_by(JobChunkModel.chunk_index)
        )
        return [self._to_entity(m) for m in result.scalars().all()]

    async def get_by_index(self, job_id: UUID, chunk_index: int) -> Optional[JobChunk]:
        """Get chunk by index."""
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
        """Update chunk status."""
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
        """Count chunks by status for a job."""
        result = await self.session.execute(
            select(JobChunkModel.status, func.count(JobChunkModel.id))
            .where(JobChunkModel.job_id == str(job_id))
            .group_by(JobChunkModel.status)
        )
        return dict(result.all())

    def _to_entity(self, model: JobChunkModel) -> JobChunk:
        """Convert ORM model to domain entity."""
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