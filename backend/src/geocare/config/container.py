"""Dependency injection container using dependency-injector."""

from dependency_injector import containers, providers

from geocare.infrastructure.queue.celery_app import create_celery_app
from geocare.config.settings import settings
from geocare.config.database import (
    engine,
    async_session_factory,
    osm_engine,
    osm_session_factory,
)
from geocare.application.use_cases.upload import UploadUseCase
from geocare.application.use_cases.processing import ProcessUseCase
from geocare.application.use_cases.reporting import ReportUseCase
from geocare.application.use_cases.export import ExportUseCase
from geocare.application.use_cases.audit import AuditUseCase
from geocare.application.use_cases.geography_refresh import GeographyRefreshUseCase
from geocare.infrastructure.persistence.repositories.chunk_repo import ChunkRepositoryImpl
from geocare.infrastructure.storage import FileStoragePort, LocalStorageClient, S3StorageClient


class DatabaseContainer(containers.DeclarativeContainer):
    """Database connections and sessions."""

    config = providers.Configuration()

    primary_engine = providers.Singleton(
        lambda: engine,
    )

    primary_session_factory = providers.Singleton(
        lambda: async_session_factory,
    )

    osm_engine = providers.Singleton(
        lambda: osm_engine,
    )

    osm_session_factory = providers.Singleton(
        lambda: osm_session_factory,
    )


class RepositoryContainer(containers.DeclarativeContainer):
    """Repository implementations."""

    database = providers.DependenciesContainer()

    # Will be wired in infrastructure container
    job_repository = providers.Factory(
        "geocare.infrastructure.persistence.repositories.job_repo.JobRepositoryImpl",
        session_factory=database.primary_session_factory,
    )

    record_repository = providers.Factory(
        "geocare.infrastructure.persistence.repositories.record_repo.RecordRepositoryImpl",
        session_factory=database.primary_session_factory,
    )

    audit_repository = providers.Factory(
        "geocare.infrastructure.persistence.repositories.audit_repo.AuditRepositoryImpl",
        session_factory=database.primary_session_factory,
    )

    user_repository = providers.Factory(
        "geocare.infrastructure.persistence.repositories.user_repo.UserRepositoryImpl",
        session_factory=database.primary_session_factory,
    )

    pincode_repository = providers.Factory(
        "geocare.infrastructure.persistence.repositories.geography_repo.PincodeRepositoryImpl",
        session_factory=database.primary_session_factory,
    )

    locality_repository = providers.Factory(
        "geocare.infrastructure.persistence.repositories.geography_repo.LocalityRepositoryImpl",
        session_factory=database.primary_session_factory,
    )

    census_repository = providers.Factory(
        "geocare.infrastructure.persistence.repositories.geography_repo.CensusRepositoryImpl",
        session_factory=database.primary_session_factory,
    )

    postgis_repository = providers.Factory(
        "geocare.infrastructure.persistence.repositories.postgis_repo.PostGISRepositoryImpl",
        session_factory=database.osm_session_factory,
    )


class GeographyContainer(containers.DeclarativeContainer):
    """Geography engine and adapters."""

    config = providers.Configuration()

    repositories = providers.DependenciesContainer()

    # Core indexes (loaded once at startup)
    pincode_index = providers.Singleton(
        "geocare.infrastructure.geography.pincode_index.PincodeIndex",
        repository=repositories.pincode_repository,
    )

    locality_fuzzy_index = providers.Singleton(
        "geocare.infrastructure.geography.locality_fuzzy.LocalityFuzzyIndex",
        repository=repositories.locality_repository,
        threshold=config.fuzzy_threshold,
    )

    census_hierarchy = providers.Singleton(
        "geocare.infrastructure.geography.census_hierarchy.CensusHierarchy",
        repository=repositories.census_repository,
    )

    # Adapters
    libpostal_adapter = providers.Singleton(
        "geocare.infrastructure.geography.parser_adapter.LibpostalAdapter",
        data_dir=config.libpostal_data_dir,
    )

    # Main orchestrator
    geography_engine = providers.Factory(
        "geocare.infrastructure.geography.engine.GeographyEngine",
        pincode_index=pincode_index,
        locality_fuzzy=locality_fuzzy_index,
        census_hierarchy=census_hierarchy,
        parser_adapter=libpostal_adapter,
        postgis_repo=repositories.postgis_repository,
    )


class QueueContainer(containers.DeclarativeContainer):
    """Celery queue and tasks."""

    config = providers.Configuration()

    celery_app = providers.Singleton(
        create_celery_app,
    )


class ApplicationContainer(containers.DeclarativeContainer):
    """Application use cases."""

    config = providers.Configuration()
    repositories = providers.DependenciesContainer()
    geography = providers.DependenciesContainer()
    queue = providers.DependenciesContainer()

    # Use cases
    upload_use_case = providers.Factory(
        UploadUseCase,
        file_storage=providers.Dependency(),
        job_repo=repositories.job_repository,
        record_repo=repositories.record_repository,
        geography_engine=geography.geography_engine,
    )

    process_use_case = providers.Factory(
        ProcessUseCase,
        job_repo=repositories.job_repository,
        chunk_repo=providers.Dependency(),
        queue=queue.celery_app,
    )

    report_use_case = providers.Factory(
        ReportUseCase,
        job_repo=repositories.job_repository,
        record_repo=repositories.record_repository,
        audit_repo=repositories.audit_repository,
    )

    export_use_case = providers.Factory(
        ExportUseCase,
        job_repo=repositories.job_repository,
        record_repo=repositories.record_repository,
        file_storage=providers.Dependency(),
    )

    audit_use_case = providers.Factory(
        AuditUseCase,
        audit_repo=repositories.audit_repository,
    )

    geography_refresh_use_case = providers.Factory(
        GeographyRefreshUseCase,
        pincode_repo=repositories.pincode_repository,
        locality_repo=repositories.locality_repository,
        census_repo=repositories.census_repository,
        postgis_repo=repositories.postgis_repository,
        geography_engine=geography.geography_engine,
    )


class InfrastructureContainer(containers.DeclarativeContainer):
    """Infrastructure implementations."""

    config = providers.Configuration()

    database = providers.Container(DatabaseContainer, config=config)
    repositories = providers.Container(
        RepositoryContainer, database=database
    )
    geography = providers.Container(GeographyContainer, config=config, repositories=repositories)
    queue = providers.Container(QueueContainer, config=config)

    # File storage - conditional based on S3 config
    file_storage = providers.Singleton(
        lambda: S3StorageClient(
            bucket=settings.S3_BUCKET,
            region=settings.S3_REGION,
            endpoint_url=settings.S3_ENDPOINT_URL,
            access_key=settings.S3_ACCESS_KEY,
            secret_key=settings.S3_SECRET_KEY,
        ) if settings.S3_BUCKET else LocalStorageClient(),
    )

    # Chunk repository (for job chunks)
    chunk_repository = providers.Factory(
        ChunkRepositoryImpl,
        session_factory=database.primary_session_factory,
    )


class Container(containers.DeclarativeContainer):
    """Main application container."""

    config = providers.Configuration(
        pydantic_settings=[settings],
    )

    infrastructure = providers.Container(
        InfrastructureContainer,
        config=config,
    )

    application = providers.Container(
        ApplicationContainer,
        config=config,
        repositories=infrastructure.repositories,
        geography=infrastructure.geography,
        queue=infrastructure.queue,
    )


# Global container instance
container = Container()
container.config.from_pydantic(settings)

# Wire dependencies after container creation to avoid circular imports
container.wire(modules=[
    "geocare.presentation.api.routes.auth",
    "geocare.presentation.api.routes.files",
    "geocare.presentation.api.routes.jobs",
    "geocare.presentation.api.routes.reports",
    "geocare.presentation.api.routes.exports",
    "geocare.presentation.api.routes.dashboard",
    "geocare.presentation.api.routes.admin",
    "geocare.presentation.ws.progress",
    "geocare.infrastructure.queue.tasks",
], packages=[
    "geocare.application",
    "geocare.infrastructure",
])