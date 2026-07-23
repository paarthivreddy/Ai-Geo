"""Celery task definitions for batch processing."""

import asyncio
from datetime import datetime
from typing import Any, Dict, List
from uuid import UUID

import polars as pl
from celery import Task, shared_task
from celery.utils.log import get_task_logger

from geocare.infrastructure.queue.celery_app import celery_app
from geocare.domain.value_objects.address import AddressInput
from geocare.domain.entities.job import ProcessingJob

logger = get_task_logger(__name__)


def get_container():
    """Lazy import to avoid circular dependency."""
    from geocare.config.container import container
    return container


class BaseTask(Task):
    """Base task with error handling and retry logic."""

    autoretry_for = (Exception,)
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True
    max_retries = 3

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        job_id = kwargs.get("job_id")
        if job_id:
            asyncio.run(self._mark_job_failed(job_id, str(exc)))

    def on_success(self, retval, task_id, args, kwargs):
        job_id = kwargs.get("job_id")
        chunk_index = kwargs.get("chunk_index")
        if job_id and chunk_index is not None:
            asyncio.run(self._update_progress(job_id, chunk_index))

    async def _mark_job_failed(self, job_id: str, error: str):
        container = get_container()
        job_repo = container.infrastructure.repositories.job_repository
        job = await job_repo.get(UUID(job_id))
        if job:
            job.fail(error)
            await job_repo.update(job)

    async def _update_progress(self, job_id: str, chunk_index: int):
        container = get_container()
        job_repo = container.infrastructure.repositories.job_repository
        job = await job_repo.get(UUID(job_id))
        if job:
            job.mark_chunk_completed(chunk_index)
            await job_repo.update(job)


@celery_app.task(base=BaseTask, bind=True, queue="standard")
def process_batch(
    self,
    job_id: str,
    chunk_index: int,
    chunk_path: str,
) -> Dict[str, Any]:
    """Process a single batch of records."""
    return asyncio.run(_process_batch_async(job_id, chunk_index, chunk_path))


async def _process_batch_async(
    job_id: str,
    chunk_index: int,
    chunk_path: str,
) -> Dict[str, Any]:
    """Async implementation of batch processing."""
    from geocare.domain.entities.job import ProcessingJob, ChunkStatus
    from geocare.infrastructure.storage import get_storage_client

    container = get_container()
    job_repo = container.infrastructure.repositories.job_repository
    chunk_repo = container.infrastructure.repositories.chunk_repository
    record_repo = container.infrastructure.repositories.record_repository
    geography_engine = container.infrastructure.geography.geography_engine

    # Get job and chunk
    job = await job_repo.get(UUID(job_id))
    if not job:
        raise ValueError(f"Job {job_id} not found")

    chunk = await chunk_repo.get_by_index(UUID(job_id), chunk_index)
    if not chunk:
        raise ValueError(f"Chunk {chunk_index} not found for job {job_id}")

    # Mark chunk as processing
    chunk.status = ChunkStatus.PROCESSING
    chunk.started_at = datetime.utcnow()
    await chunk_repo.update(chunk)

    try:
        # Load chunk data
        storage = get_storage_client()
        df = pl.read_parquet(chunk_path)

        # Process each row
        results = []
        for i, row in enumerate(df.iter_rows(named=True)):
            result = await _process_record(row, job, geography_engine)
            results.append(result)

        # Save records
        await record_repo.bulk_create(results)

        # Update chunk
        chunk.status = ChunkStatus.COMPLETED
        chunk.completed_at = datetime.utcnow()
        chunk.row_count = len(results)
        await chunk_repo.update(chunk)

        # Update job progress
        succeeded = sum(1 for r in results if r.confidence_score.get("overall", 0) >= 60)
        failed = len(results) - succeeded

        job.mark_chunk_completed(chunk_index)
        await job_repo.update(job)

        # Publish progress
        container = get_container()
        progress_publisher = container.infrastructure.queue.progress_publisher
        await progress_publisher.publish_progress(
            job_id=job_id,
            processed=job.processed_rows,
            total=job.total_rows,
            current_batch=len(job.completed_chunks),
            total_batches=job.total_chunks,
        )
        await progress_publisher.publish_batch_complete(
            job_id=job_id,
            batch_index=chunk_index,
            succeeded=succeeded,
            failed=failed,
        )

        return {
            "job_id": job_id,
            "chunk_index": chunk_index,
            "processed": len(results),
            "succeeded": succeeded,
            "failed": failed,
        }

    except Exception as e:
        # Mark chunk as failed
        chunk.status = ChunkStatus.FAILED
        chunk.error_message = str(e)
        chunk.retry_count += 1
        chunk.completed_at = datetime.utcnow()
        await chunk_repo.update(chunk)

        # Update job
        job.mark_chunk_failed(chunk_index)
        await job_repo.update(job)

        raise


async def _process_record(
    row: Dict[str, Any],
    job: ProcessingJob,
    geography_engine,
) -> Any:
    """Process a single record through the enrichment pipeline."""
    from geocare.domain.entities.record import PatientRecord
    from geocare.domain.value_objects.address import AddressInput
    from geocare.domain.value_objects.confidence import ConfidenceScore

    # Build address input from column mapping
    mapping = job.column_mapping
    address = AddressInput(
        line1=row.get(mapping.address_line_1) if mapping.address_line_1 else None,
        line2=row.get(mapping.address_line_2) if mapping.address_line_2 else None,
        landmark=row.get(mapping.landmark) if mapping.landmark else None,
        pincode=row.get(mapping.pincode) if mapping.pincode else None,
        city=row.get(mapping.city) if mapping.city else None,
        district=row.get(mapping.district) if mapping.district else None,
        state=row.get(mapping.state) if mapping.state else None,
        country=row.get(mapping.country) if mapping.country else "India",
    )

    # Normalize
    normalized = _normalize_address(address)

    # Parse with libpostal
    parsed = await geography_engine.parse_address(normalized.get_concatenated())

    # Enrich with geography
    enriched, confidence = await geography_engine.enrich_address(
        address_input=normalized,
        parsed_address=parsed,
    )

    # Create record
    record = PatientRecord(
        job_id=job.id,
        row_index=row.get("_row_index", 0),
        patient_id_hash=row.get("patient_id_hash", ""),
        original_address=address.to_dict(),
        normalized_address=normalized.to_dict(),
        parsed_address=parsed.to_dict() if hasattr(parsed, 'to_dict') else parsed,
        enriched_address=enriched.to_dict() if hasattr(enriched, 'to_dict') else enriched,
        confidence_score=confidence.to_dict() if hasattr(confidence, 'to_dict') else confidence,
        confidence_tier=confidence.get("tier", "unverified"),
        match_method=confidence.get("method", "manual"),
    )

    return record


def _normalize_address(address: AddressInput) -> AddressInput:
    """Normalize address components."""
    import re

    def clean(text: str) -> str:
        if not text:
            return None
        text = text.strip()
        text = re.sub(r'\s+', ' ', text)
        # Expand abbreviations
        abbrevs = {
            r'\bRd\b': 'Road',
            r'\bSt\b': 'Street',
            r'\bAve\b': 'Avenue',
            r'\bNgr\b': 'Nagar',
            r'\bClny\b': 'Colony',
            r'\bExtn\b': 'Extension',
            r'\bSec\b': 'Sector',
            r'\bBlk\b': 'Block',
            r'\bPh\b': 'Phase',
        }
        for pat, repl in abbrevs.items():
            text = re.sub(pat, repl, text, flags=re.IGNORECASE)
        return text

    return AddressInput(
        line1=clean(address.line1),
        line2=clean(address.line2),
        landmark=clean(address.landmark),
        pincode=clean(address.pincode),
        city=clean(address.city),
        district=clean(address.district),
        state=clean(address.state),
        country=clean(address.country),
    )


@celery_app.task(base=BaseTask, bind=True, queue="high")
def profile_file(self, job_id: str, file_path: str) -> Dict[str, Any]:
    """Profile uploaded file and detect address columns."""
    return asyncio.run(_profile_file_async(job_id, file_path))


async def _profile_file_async(job_id: str, file_path: str) -> Dict[str, Any]:
    """Async implementation of file profiling."""
    import polars as pl

    job_repo = container.infrastructure.repositories.job_repository
    job = await job_repo.get(UUID(job_id))
    if not job:
        raise ValueError(f"Job {job_id} not found")

    job.status = "profiling"
    await job_repo.update(job)

    # Read file
    if file_path.endswith(".csv"):
        df = pl.read_csv(file_path, n_rows=10000)
        full_df = pl.read_csv(file_path)
    else:
        df = pl.read_excel(file_path, n_rows=10000)
        full_df = pl.read_excel(file_path)

    # Analyze columns
    columns = []
    for col_name in df.columns:
        col = df[col_name]
        null_pct = col.null_count() / len(df) * 100
        sample = col.drop_nulls().head(5).to_list()

        columns.append({
            "name": col_name,
            "dtype": str(col.dtype),
            "null_pct": round(null_pct, 2),
            "distinct_count": col.n_unique(),
            "sample_values": sample,
        })

    # Detect address columns
    detected = _detect_address_columns(df, columns)

    job.detected_address_columns = detected
    job.total_rows = len(full_df)
    job.total_columns = len(df.columns)
    job.status = "mapping"
    await job_repo.update(job)

    return {
        "job_id": job_id,
        "row_count": len(full_df),
        "column_count": len(df.columns),
        "columns": columns,
        "detected_address_columns": detected,
    }


def _detect_address_columns(df, columns: List[Dict]) -> List[str]:
    """Detect address-related columns."""
    address_keywords = {
        "address", "addr", "street", "road", "lane", "avenue",
        "locality", "area", "colony", "nagar", "sector", "block",
        "city", "town", "village", "district", "dist", "state",
        "pincode", "pin", "zip", "postal",
        "landmark", "near", "opp", "behind",
        "house", "flat", "apartment", "apt", "floor", "building",
    }

    detected = []
    for col in columns:
        name_lower = col["name"].lower()
        if any(kw in name_lower for kw in address_keywords):
            detected.append(col["name"])
            continue

        # Check sample values
        if col["sample_values"]:
            sample_text = " ".join(str(v).lower() for v in col["sample_values"])
            if any(kw in sample_text for kw in address_keywords):
                detected.append(col["name"])
                continue

            # Check for PIN code pattern
            if any(re.match(r"^[1-8]\d{5}$", str(v)) for v in col["sample_values"][:10]):
                detected.append(col["name"])

    return detected


@celery_app.task(base=BaseTask, bind=True, queue="low")
def export_results(self, job_id: str, format: str, filters: Dict) -> str:
    """Generate export file."""
    return asyncio.run(_export_results_async(job_id, format, filters))


async def _export_results_async(job_id: str, format: str, filters: Dict) -> str:
    """Async export implementation."""
    export_uc = container.application.export_use_case
    export_path = await export_uc.export_job(
        job_id=UUID(job_id),
        format=format,
        confidence_tiers=filters.get("confidence_tiers"),
        include_audit=filters.get("include_audit", False),
        include_original=filters.get("include_original", True),
    )
    return export_path


@celery_app.task(base=BaseTask, bind=True, queue="low")
def generate_report(self, job_id: str) -> Dict[str, Any]:
    """Generate quality report."""
    return asyncio.run(_generate_report_async(job_id))


async def _generate_report_async(job_id: str) -> Dict[str, Any]:
    """Async report generation."""
    report_uc = container.application.report_use_case
    report = await report_uc.generate_report(UUID(job_id))
    return report.to_dict()