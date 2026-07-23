"""Reporting use case for quality analysis."""

from typing import Optional, List
from uuid import UUID
from datetime import datetime

from geocare.domain.value_objects.quality import QualityReport, QualityMetrics, QualityDelta
from geocare.domain.entities.job import JobQualityStats
from geocare.domain.ports.repositories import JobRepository, RecordRepository, AuditRepository


class ReportUseCase:
    """Generate quality reports for processing jobs."""

    def __init__(
        self,
        job_repo: JobRepository,
        record_repo: RecordRepository,
        audit_repo: AuditRepository,
    ):
        self.job_repo = job_repo
        self.record_repo = record_repo
        self.audit_repo = audit_repo

    async def generate_report(self, job_id: UUID) -> QualityReport:
        """Generate comprehensive quality report for a completed job."""
        job = await self.job_repo.get(job_id)
        if not job:
            raise ValueError("Job not found")

        if job.status.value != "completed":
            raise ValueError("Report only available for completed jobs")

        # Get quality stats from job
        stats = job.quality_stats
        if not stats:
            raise ValueError("Quality stats not available")

        # Get confidence distribution from records
        confidence_counts = await self.record_repo.count_by_confidence(job_id)
        review_counts = await self.record_repo.count_by_status(job_id)

        # Build before metrics
        before = QualityMetrics(
            total_records=stats.total_records or 0,
            complete_addresses=stats.complete_addresses_before or 0,
            missing_pincode=stats.missing_pincode_before or 0,
            missing_locality=stats.missing_locality_before or 0,
            missing_city=stats.missing_city_before or 0,
            missing_district=stats.missing_district_before or 0,
            missing_state=stats.missing_state_before or 0,
            invalid_addresses=stats.invalid_addresses_before or 0,
            duplicate_addresses=stats.duplicate_addresses_before or 0,
            overall_quality_pct=stats.overall_quality_before or 0,
        )

        # Build after metrics
        after = QualityMetrics(
            total_records=stats.total_records or 0,
            complete_addresses=(stats.complete_addresses_before or 0) + (stats.improved_records or 0),
            missing_pincode=max(0, (stats.missing_pincode_before or 0) - (stats.pincodes_added or 0)),
            missing_locality=max(0, (stats.missing_locality_before or 0) - (stats.cities_added or 0)),  # approximate
            missing_city=max(0, (stats.missing_city_before or 0) - (stats.cities_added or 0)),
            missing_district=max(0, (stats.missing_district_before or 0) - (stats.districts_added or 0)),
            missing_state=max(0, (stats.missing_state_before or 0) - (stats.states_added or 0)),
            invalid_addresses=max(0, (stats.invalid_addresses_before or 0) - (stats.improved_records or 0)),
            duplicate_addresses=stats.duplicate_addresses_before or 0,
            overall_quality_pct=stats.final_quality_score or 0,
        )

        # Build delta
        delta = QualityDelta(
            pincodes_added=stats.pincodes_added or 0,
            cities_added=stats.cities_added or 0,
            districts_added=stats.districts_added or 0,
            states_added=stats.states_added or 0,
            spell_corrections=stats.spell_corrections or 0,
            improved_records=stats.improved_records or 0,
            manual_review_records=stats.manual_review_records or 0,
            quality_improvement_pct=stats.improvement_percentage or 0,
            fill_rate=0,  # calculated below
        )

        total = stats.total_records or 1
        delta.fill_rate = (
            (stats.pincodes_added or 0) +
            (stats.cities_added or 0) +
            (stats.districts_added or 0) +
            (stats.states_added or 0)
        ) / total * 100

        # Confidence distribution
        confidence_dist = {
            "high": stats.confidence_high or 0,
            "medium": stats.confidence_medium or 0,
            "low": stats.confidence_low or 0,
            "unverified": stats.confidence_unverified or 0,
        }

        return QualityReport(
            before=before,
            after=after,
            delta=delta,
            confidence_distribution=confidence_dist,
            generated_at=datetime.utcnow(),
        )

    async def export_report(
        self,
        job_id: UUID,
        format: str = "json",
    ) -> bytes:
        """Export report in specified format."""
        report = await self.generate_report(job_id)

        if format == "json":
            import json
            return json.dumps(report.to_dict(), indent=2).encode()
        elif format == "csv":
            import csv
            import io
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["Metric", "Before", "After", "Delta"])
            for key, val in report.before.__dict__.items():
                writer.writerow([key, val, getattr(report.after, key, ""), ""])
            for key, val in report.delta.__dict__.items():
                writer.writerow([key, "", "", val])
            return output.getvalue().encode()
        elif format == "pdf":
            # Would use reportlab or weasyprint
            return b"PDF export not implemented"
        else:
            raise ValueError(f"Unsupported format: {format}")