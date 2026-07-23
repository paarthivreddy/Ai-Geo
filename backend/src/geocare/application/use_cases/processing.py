"""Processing use case for batch job orchestration."""

from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4
from datetime import datetime

from geocare.domain.entities.job import ProcessingJob, JobStatus, ChunkStatus
from geocare.domain.ports.repositories import JobRepository, ChunkRepository
from geocare.domain.ports.queue import QueuePort, ProgressPublisherPort


class ProcessUseCase:
    """Use case for managing batch processing jobs."""

    def __init__(
        self,
        job_repo: JobRepository,
        chunk_repo: ChunkRepository,
        queue: QueuePort,
        progress: ProgressPublisherPort,
    ):
        self.job_repo = job_repo
        self.chunk_repo = chunk_repo
        self.queue = queue
        self.progress = progress

    async def create_and_start_job(
        self,
        file_id: UUID,
        column_mapping: Dict[str, str],
        chunk_size: int,
        user_id: UUID,
    ) -> ProcessingJob:
        """Create and start a processing job (called from upload use case)."""
        # This would be called from upload use case after chunking
        # For now, just return the job created by upload
        pass

    async def get_job(self, job_id: UUID) -> Optional[ProcessingJob]:
        """Get job by ID."""
        return await self.job_repo.get(job_id)

    async def list_jobs(
        self,
        user_id: UUID,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[List[ProcessingJob], int]:
        """List jobs for user with pagination."""
        jobs = await self.job_repo.get_by_user(user_id, limit, offset, status)
        total = await self.job_repo.count_by_user(user_id)
        return jobs, total

    async def cancel_job(self, job_id: UUID, reason: Optional[str] = None) -> ProcessingJob:
        """Cancel a running job."""
        job = await self.job_repo.get(job_id)
        if not job:
            raise ValueError("Job not found")

        if job.is_terminal():
            raise ValueError(f"Job is already {job.status.value}")

        job.cancel(reason)
        return await self.job_repo.update(job)

    async def retry_job(self, job_id: UUID) -> ProcessingJob:
        """Retry a failed job from failed chunks."""
        job = await self.job_repo.get(job_id)
        if not job:
            raise ValueError("Job not found")

        if not job.can_retry():
            raise ValueError("Job cannot be retried")

        # Reset failed chunks for retry
        job.status = JobStatus.QUEUED
        job.error_message = None
        job.started_at = None
        job.completed_at = None

        # Reset failed chunks to pending
        # This would be done via chunk repository
        # For now, just update job

        return await self.job_repo.update(job)

    async def stream_progress(self, job_id: UUID):
        """Stream progress updates via SSE."""
        # This would connect to the queue's progress publisher
        # For SSE, we'd yield progress updates
        pass


class ChunkProcessor:
    """Process individual chunks in background workers."""

    def __init__(
        self,
        job_repo: JobRepository,
        chunk_repo: ChunkRepository,
        queue: QueuePort,
        progress: ProgressPublisherPort,
    ):
        self.job_repo = job_repo
        self.chunk_repo = chunk_repo
        self.queue = queue
        self.progress = progress

    async def process_chunk(
        self,
        job_id: UUID,
        chunk_index: int,
        chunk_path: str,
    ) -> Dict[str, Any]:
        """Process a single chunk of records."""
        import polars as pl

        job = await self.job_repo.get(job_id)
        if not job:
            raise ValueError("Job not found")

        # Mark chunk as processing
        chunk = await self.chunk_repo.get_by_index(job_id, chunk_index)
        if not chunk:
            raise ValueError(f"Chunk {chunk_index} not found")

        chunk.status = ChunkStatus.PROCESSING
        chunk.started_at = datetime.utcnow()
        await self.chunk_repo.update(chunk)

        try:
            # Load chunk
            df = pl.read_parquet(chunk_path)

            # Process each row
            results = []
            for row in df.iter_rows(named=True):
                result = await self._process_record(row, job)
                results.append(result)

            # Save results (would use record repository)
            # await self._save_results(job_id, results)

            # Update chunk status
            chunk.status = ChunkStatus.COMPLETED
            chunk.completed_at = datetime.utcnow()
            await self.chunk_repo.update(chunk)

            # Update job progress
            job.mark_chunk_completed(chunk_index)
            await self.job_repo.update(job)

            # Publish progress
            await self.progress.publish_progress(
                job_id=str(job_id),
                processed=job.processed_rows,
                total=job.total_rows,
                current_batch=job.completed_chunks.__len__(),
                total_batches=job.total_chunks,
            )

            await self.progress.publish_batch_complete(
                job_id=str(job_id),
                batch_index=chunk_index,
                succeeded=sum(1 for r in results if r["success"]),
                failed=sum(1 for r in results if not r["success"]),
            )

            return {
                "job_id": str(job_id),
                "chunk_index": chunk_index,
                "processed": len(results),
                "succeeded": sum(1 for r in results if r["success"]),
                "failed": sum(1 for r in results if not r["success"]),
            }

        except Exception as e:
            # Mark chunk as failed
            chunk.status = ChunkStatus.FAILED
            chunk.error_message = str(e)
            chunk.retry_count += 1
            chunk.completed_at = datetime.utcnow()
            await self.chunk_repo.update(chunk)

            # Update job
            job.mark_chunk_failed(chunk_index)
            await self.job_repo.update(job)

            # Retry if under max retries
            if chunk.retry_count < chunk.max_retries:
                # Re-queue
                await self.queue.enqueue(
                    "process_chunk",
                    job_id=str(job_id),
                    chunk_index=chunk_index,
                    chunk_path=chunk_path,
                )

            raise

    async def _process_record(
        self,
        row: Dict[str, Any],
        job: ProcessingJob,
    ) -> Dict[str, Any]:
        """Process a single record through the enrichment pipeline."""
        # This would call the geography engine
        # For now, return placeholder
        return {
            "success": True,
            "enriched_address": {},
            "confidence_score": {"overall": 85, "tier": "high", "method": "exact"},
        }