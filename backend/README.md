# GeoCare AI Backend

FastAPI backend for the India Patient Address Intelligence Platform.

## Overview

This is the backend API for GeoCare AI, an enterprise-grade, offline-first platform for enriching and validating Indian patient addresses from healthcare datasets.

## Tech Stack

- **FastAPI** - Modern, fast web framework for building APIs
- **SQLAlchemy 2.0** - Async ORM with PostgreSQL + PostGIS
- **Celery + Redis** - Distributed task queue for batch processing
- **Polars** - High-performance DataFrame library for data processing
- **libpostal + RapidFuzz** - Address parsing and fuzzy matching
- **dependency-injector** - Dependency injection container
- **Pydantic v2** - Data validation and settings management
- **Prometheus Client** - Metrics exposition

## Project Structure

```
src/geocare/
├── config/                 # Configuration & DI container
│   ├── settings.py         # Pydantic settings
│   ├── container.py        # Dependency injection
│   ├── database.py         # Database connections
│   └── logging.py          # Structured logging
├── domain/                 # Domain layer (pure Python)
│   ├── entities/           # Domain entities
│   ├── value_objects/      # Value objects
│   ├── ports/              # Repository interfaces
│   └── services/           # Domain services
├── application/            # Application layer
│   ├── use_cases/          # Use cases / interactors
│   ├── dto/                # Data transfer objects
│   └── commands/           # Commands
├── infrastructure/         # Infrastructure layer
│   ├── persistence/        # SQLAlchemy repositories
│   ├── geography/          # Geography engine & adapters
│   ├── queue/              # Celery tasks
│   ├── storage/            # File storage (S3/local)
│   └── security/           # Auth, JWT, encryption
├── presentation/           # Presentation layer
│   ├── api/                # FastAPI routes
│   └── ws/                 # WebSocket handlers
└── main.py                 # Application entry point
```

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 16 + PostGIS 3.4
- Redis 7
- libpostal (system dependency)

### Installation

```bash
cd backend
pip install -e ".[dev,geo]"
```

### Environment Setup

```bash
cp .env.example .env
# Edit .env with your database/redis credentials
```

### Database Migrations

```bash
alembic upgrade head
```

### Run Development Server

```bash
uvicorn geocare.main:app --reload --host 0.0.0.0 --port 8000
```

### Run Celery Worker

```bash
celery -A geocare.infrastructure.queue.celery_app worker -l info -c 4
```

### Run Celery Beat (Scheduler)

```bash
celery -A geocare.infrastructure.queue.celery_app beat -l info
```

## API Documentation

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json

## Key Features

1. **File Upload & Profiling** - CSV/Excel upload with auto column detection
2. **Address Enrichment** - PIN codes, localities, city/district/state hierarchy
3. **Confidence Scoring** - Weighted 0-100 scores with tier classification
4. **Batch Processing** - Chunked parallel processing up to 10M records
5. **Audit Trail** - Immutable per-field transformation logs
6. **Real-time Progress** - SSE/WebSocket job progress streaming
7. **Analytics Dashboard** - KPIs, geographic heatmaps, quality trends
8. **Export** - CSV, Excel, Parquet with filtering

## Architecture

Follows Clean Architecture with strict layer boundaries:

```
Presentation → Application → Domain ← Infrastructure
```

Dependency rule: Inner layers never depend on outer layers.

## Testing

```bash
# Unit tests
pytest tests/unit -v

# Integration tests
pytest tests/integration -v

# Coverage
pytest --cov=geocare --cov-report=html
```

## License

MIT