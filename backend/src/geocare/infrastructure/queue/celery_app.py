"""Celery application configuration."""

from celery import Celery
from celery.signals import worker_init, worker_shutdown

from geocare.config.settings import settings


def create_celery_app() -> Celery:
    """Create and configure Celery application."""
    app = Celery("geocare")

    app.conf.update(
        # Broker and backend
        broker_url=settings.CELERY_BROKER_URL,
        result_backend=settings.CELERY_RESULT_BACKEND,

        # Task serialization
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],

        # Timezone
        timezone="UTC",
        enable_utc=True,

        # Task routing
        task_routes={
            "geocare.infrastructure.queue.tasks.process_batch": {"queue": "standard"},
            "geocare.infrastructure.queue.tasks.profile_file": {"queue": "high"},
            "geocare.infrastructure.queue.tasks.export_results": {"queue": "low"},
            "geocare.infrastructure.queue.tasks.generate_report": {"queue": "low"},
        },

        # Worker configuration
        worker_prefetch_multiplier=1,
        task_acks_late=True,
        task_reject_on_worker_lost=True,

        # Retry policy
        task_default_retry_delay=60,
        task_max_retries=3,
        task_retry_backoff=True,
        task_retry_backoff_max=600,
        task_retry_jitter=True,

        # Result expiration
        result_expires=86400,  # 24 hours

        # Monitoring
        worker_send_task_events=True,
        task_send_sent_event=True,
    )

    # Auto-discover tasks
    app.autodiscover_tasks([
        "geocare.infrastructure.queue.tasks",
    ])

    return app


# Create the app instance
celery_app = create_celery_app()


@worker_init.connect
def on_worker_init(**kwargs):
    """Initialize worker (load geography indexes, etc.)."""
    import logging
    logging.info("Celery worker initializing...")


@worker_shutdown.connect
def on_worker_shutdown(**kwargs):
    """Cleanup on worker shutdown."""
    import logging
    logging.info("Celery worker shutting down...")