"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    APP_NAME: str = "GeoCare AI"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"

    # Database
    DATABASE_URL: str = Field(default="postgresql+asyncpg://postgres:postgres@localhost:7117/geocare", description="Primary PostgreSQL connection string")
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    # OSM PostGIS
    OSM_DATABASE_URL: str = Field(default="postgresql+asyncpg://postgres:postgres@localhost:7117/osm", description="OSM PostGIS connection string")

    # Redis
    REDIS_URL: str = Field(default="redis://localhost:6379/0", description="Redis connection string")
    REDIS_CLUSTER_URLS: str = Field(default="", description="Comma-separated Redis cluster URLs")

    @field_validator("REDIS_CLUSTER_URLS", mode="after")
    @classmethod
    def parse_redis_cluster_urls(cls, v: str) -> List[str]:
        if isinstance(v, str) and v:
            return [url.strip() for url in v.split(",") if url.strip()]
        return []

    # Celery
    CELERY_BROKER_URL: str = Field(default="redis://localhost:6379/1", description="Celery broker URL")
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/2", description="Celery result backend URL")
    CELERY_CONCURRENCY: int = 4
    CELERY_TASK_ACKS_LATE: bool = True
    CELERY_TASK_REJECT_ON_WORKER_LOST: bool = True

    # Geography Data
    GEOGRAPHY_DATA_PATH: str = Field(default="/data/geography", description="Geography data directory path")
    LIBPOSTAL_DATA_DIR: str = Field(default="/usr/local/share/libpostal", description="Libpostal data directory path")

    # File Upload
    MAX_FILE_SIZE_MB: int = 2048
    UPLOAD_DIR: str = Field(default="/data/uploads", description="Upload directory path")
    CHUNK_DIR: str = Field(default="/data/chunks", description="Chunk directory path")
    ALLOWED_EXTENSIONS: str = Field(default=".csv,.xlsx,.xls", description="Comma-separated file extensions")

    @field_validator("ALLOWED_EXTENSIONS", mode="after")
    @classmethod
    def parse_allowed_extensions(cls, v: str) -> List[str]:
        if isinstance(v, str):
            return [ext.strip() for ext in v.split(",") if ext.strip()]
        return v

    # Processing
    DEFAULT_CHUNK_SIZE: int = 50000
    MAX_CHUNK_SIZE: int = 200000
    MIN_CHUNK_SIZE: int = 5000
    FUZZY_THRESHOLD: int = 85

    # Auth
    JWT_SECRET_KEY: str = Field(default="dev-secret-change-in-production", description="JWT signing secret")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    BCRYPT_ROUNDS: int = 12

    # Security
    CORS_ORIGINS: str = Field(default="http://localhost:3000,http://localhost:8000", description="Comma-separated CORS origins")
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    @field_validator("CORS_ORIGINS", mode="after")
    @classmethod
    def parse_cors_origins(cls, v: str) -> List[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # Monitoring
    PROMETHEUS_METRICS_ENABLED: bool = True
    PROMETHEUS_PORT: int = 9090

    # S3/MinIO Storage
    S3_BUCKET: str = Field(default="", description="S3 bucket name")
    S3_REGION: str = Field(default="us-east-1", description="S3 region")
    S3_ENDPOINT_URL: str = Field(default="", description="S3 endpoint URL (for MinIO)")
    S3_ACCESS_KEY: str = Field(default="", description="S3 access key")
    S3_SECRET_KEY: str = Field(default="", description="S3 secret key")

    # Derived properties
    @property
    def max_file_size_bytes(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024

    @property
    def allowed_mime_types(self) -> set[str]:
        return {
            "text/csv",
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()