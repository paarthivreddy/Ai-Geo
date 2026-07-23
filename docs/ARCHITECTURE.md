# System Architecture

## GeoCare AI – India Patient Address Intelligence Platform

**Version:** 1.0  
**Status:** Draft  
**Date:** 2025-07-17  
**Classification:** Internal – Enterprise Use Only

---

## 1. High-Level Architecture

### 1.1 System Context

GeoCare AI is an **offline-first, batch-oriented data enrichment platform** designed for healthcare organizations in India. It transforms raw, incomplete patient address records into standardized, validated, and enriched geographic data using only open-source datasets and libraries.

```mermaid
C4Context
    title System Context Diagram – GeoCare AI

    Person(hospital_user, "Hospital Staff", "Uploads patient CSV/Excel files, reviews results")
    Person(data_analyst, "Data Analyst", "Consumes enriched datasets for reporting")
    Person(admin, "System Admin", "Manages users, monitors jobs, updates geography data")

    System(geocare, "GeoCare AI", "Patient address enrichment platform")

    System_Ext(india_post, "India Post", "Official PIN code directory (CSV)")
    System_Ext(osm, "OpenStreetMap", "India PBF extract (geofabrik.de)")
    System_Ext(census, "Census of India", "Village/Town hierarchy (CSV)")
    System_Ext(libpostal, "libpostal", "C library for address parsing")

    Rel(hospital_user, geocare, "Upload files, review results", "HTTPS")
    Rel(data_analyst, geocare, "Download enriched data", "HTTPS")
    Rel(admin, geocare, "Admin operations", "HTTPS")
    Rel(geocare, india_post, "Download PIN dataset (quarterly)", "HTTPS")
    Rel(geocare, osm, "Download India PBF (quarterly)", "HTTPS")
    Rel(geocare, census, "Download hierarchy (annual)", "HTTPS")
    Rel(geocare, libpostal, "Link at runtime", "Native lib")
```

### 1.2 Core Design Principles

| Principle | Implementation |
|-----------|----------------|
| **Offline-First** | All geography data pre-downloaded; zero runtime API calls |
| **Open-Source Only** | India Post CSV, OSM PBF, Census CSV, libpostal, RapidFuzz, Polars, PostGIS |
| **Clean Architecture** | Domain layer isolated from infrastructure; dependency inversion throughout |
| **Batch-Oriented** | Celery workers process chunks; no streaming/real-time requirements |
| **Audit-First** | Every field transformation logged immutably |
| **Scalable to 10M** | Horizontal worker scaling, Polars streaming, chunked I/O |
| **Healthcare-Grade** | PII protection, encryption at rest, role-based access, audit trail |

### 1.3 High-Level Component Topology

```mermaid
C4Container
    title Container Diagram – GeoCare AI

    Container(frontend, "Frontend", "Next.js, React, TypeScript, Tailwind, ECharts", "Upload, profiling, dashboard, export")
    Container(backend, "Backend API", "FastAPI, Python 3.11+, Pydantic", "Auth, file upload, job management, results API")
    Container(worker, "Worker Service", "Celery + Redis, Python", "Batch processing: parse, enrich, score, audit")
    ContainerDb(db, "PostgreSQL + PostGIS", "SQLAlchemy, asyncpg", "Jobs, records, audit, geography reference data")
    ContainerDb(redis, "Redis", "Celery broker, result backend, fuzzy cache", "Queue, cache, pub/sub")
    Container(geography, "Geography Engine", "Python (Polars, RapidFuzz, libpostal, GeoPandas)", "PIN index, locality fuzzy, parser, PostGIS loader")
    ContainerDb(osm_db, "OSM PostGIS", "PostGIS raster/vector", "Boundary polygons for choropleth")

    Rel(frontend, backend, "REST + WebSocket", "HTTPS/WSS")
    Rel(backend, worker, "Enqueue jobs", "Redis")
    Rel(backend, db, "CRUD", "asyncpg")
    Rel(worker, db, "Read/write", "asyncpg")
    Rel(worker, redis, "Queue / Cache", "Redis protocol")
    Rel(worker, geography, "Call engine", "In-process")
    Rel(geography, db, "Load reference", "COPY / SQL")
    Rel(geography, osm_db, "Spatial queries", "PostGIS")
```

---

## 2. Business Architecture

### 2.1 Business Capability Map

```mermaid
mindmap
  root((GeoCare AI))
    Data Ingestion
      File Upload
      Format Validation
      Column Detection
      Column Mapping
    Data Profiling
      Column Statistics
      Quality Baseline
      Missing Geography
      Duplicate Detection
    Address Processing
      Normalization
      Parsing
      Spelling Correction
      PIN Resolution
      Locality Resolution
      City/District/State Enrichment
    Quality Assessment
      Confidence Scoring
      Tier Classification
      Review Queue
    Audit & Compliance
      Transformation Log
      Before/After Reports
      Export Audit Trail
    Analytics & Reporting
      KPI Dashboard
      Geographic Heatmaps
      Quality Trends
      Export Enriched Data
    Administration
      User Management
      Geography Data Updates
      Job Monitoring
      System Health
```

### 2.2 Key Business Processes

| Process | Trigger | SLA | Owner |
|---------|---------|-----|-------|
| **Batch Enrichment** | User uploads file | 500K rows < 30 min | Data Engineer |
| **Geography Refresh** | Quarterly schedule | < 4 hours | Data Engineer |
| **Quality Review** | Job completes | Interactive | Data Analyst |
| **Export Delivery** | User requests | Streaming | Data Analyst |

### 2.3 Stakeholder Concerns

| Stakeholder | Primary Concerns |
|-------------|------------------|
| Hospital IT | Data sovereignty, offline operation, integration simplicity |
| Data Analyst | Accuracy, confidence scores, export formats, audit trail |
| Compliance Officer | PII handling, immutable logs, data retention |
| DevOps | Horizontal scaling, observability, zero-downtime deploys |
| Data Engineer | Geography data freshness, fuzzy match accuracy, processing throughput |

---

## 3. Logical Architecture

### 3.1 Layered Architecture (Clean Architecture)

```mermaid
graph TB
    subgraph Presentation["Presentation Layer"]
        FE[Next.js Frontend]
        API[FastAPI Routes]
        WS[WebSocket Handler]
    end

    subgraph Application["Application Layer"]
        UC[Use Cases / Interactors]
        DTO[DTOs / Commands / Queries]
        PORT[Ports (Interfaces)]
    end

    subgraph Domain["Domain Layer"]
        ENT[Entities]
        VO[Value Objects]
        EVT[Domain Events]
        REPO_I[Repository Interfaces]
        SVC_I[Domain Services Interfaces]
    end

    subgraph Infrastructure["Infrastructure Layer"]
        REPO[Repository Implementations]
        GEO[Geography Engine Adapter]
        PARSER[libpostal Adapter]
        FUZZY[RapidFuzz Adapter]
        QUEUE[Celery Adapter]
        DB[PostgreSQL/PostGIS]
        CACHE[Redis]
        FS[File Storage]
    end

    FE --> API
    API --> UC
    WS --> UC
    UC --> PORT
    PORT -.-> REPO_I
    PORT -.-> SVC_I
    REPO_I <.. REPO
    SVC_I <.. GEO
    SVC_I <.. PARSER
    SVC_I <.. FUZZY
    UC -.-> QUEUE
    REPO --> DB
    GEO --> DB
    GEO --> CACHE
    QUEUE --> CACHE
```

### 3.2 Domain Model Overview

```mermaid
classDiagram
    class ProcessingJob {
        +id: UUID
        +user_id: UUID
        +filename: str
        +total_rows: int
        +status: JobStatus
        +column_mapping: ColumnMapping
        +started_at: DateTime
        +completed_at: DateTime?
        +progress: float
        +error: str?
    }

    class PatientRecord {
        +id: UUID
        +job_id: UUID
        +row_index: int
        +patient_id: str?
        +original_address: AddressInput
        +enriched_address: EnrichedAddress?
        +confidence: ConfidenceScore
        +review_status: ReviewStatus
        +created_at: DateTime
        +updated_at: DateTime
    }

    class AddressInput {
        +line1: str?
        +line2: str?
        +landmark: str?
        +pincode: str?
        +city: str?
        +district: str?
        +state: str?
        +country: str?
    }

    class EnrichedAddress {
        +line1: str
        +line2: str?
        +locality: Locality
        +city: City
        +district: District
        +state: State
        +pincode: Pincode
        +country: Country
        +formatted: str
    }

    class ConfidenceScore {
        +overall: int  # 0-100
        +pincode: int
        +locality: int
        +city: int
        +district: int
        +state: int
        +parsing: int
        +method: MatchMethod
        +tier: ConfidenceTier
    }

    class AuditEntry {
        +id: UUID
        +record_id: UUID
        +field: str
        +old_value: str?
        +new_value: str?
        +method: ProcessingMethod
        +confidence: int
        +source: DataSource
        +timestamp: DateTime
        +user_id: UUID?
    }

    class Pincode {
        +code: str  # 6-digit
        +office_name: str
        +office_type: OfficeType
        +delivery_status: DeliveryStatus
        +district: str
        +state: str
        +taluk: str?
        +circle: str
        +region: str
        +division: str
        +latitude: float?
        +longitude: float?
    }

    class Locality {
        +name: str
        +canonical_name: str
        +pincode: str
        +city: str
        +district: str
        +state: str
        +aliases: List[str]
        +source: DataSource
        +geometry: Geometry?
    }

    ProcessingJob "1" --> "*" PatientRecord
    PatientRecord "1" --> "1" AddressInput
    PatientRecord "1" --> "0..1" EnrichedAddress
    PatientRecord "1" --> "1" ConfidenceScore
    PatientRecord "1" --> "*" AuditEntry
    EnrichedAddress --> Pincode
    EnrichedAddress --> Locality
    EnrichedAddress --> City
    EnrichedAddress --> District
    EnrichedAddress --> State
    EnrichedAddress --> Country
```

### 3.3 Module Boundaries

| Module | Responsibility | Depends On |
|--------|----------------|------------|
| `geocare.domain` | Core entities, value objects, events, repository interfaces | None (pure Python) |
| `geocare.application` | Use cases, DTOs, ports (interfaces) | `domain` |
| `geocare.infrastructure.persistence` | SQLAlchemy repositories, migrations | `domain`, `application` |
| `geocare.infrastructure.geography` | PIN index, fuzzy matcher, parser adapter, PostGIS loader | `domain`, `application` |
| `geocare.infrastructure.queue` | Celery tasks, result handling | `application` |
| `geocare.presentation.api` | FastAPI routers, request/response schemas | `application` |
| `geocare.presentation.ws` | WebSocket progress updates | `application` |
| `geocare.config` | Settings, dependency injection container | All |

---

## 4. Physical Architecture

### 4.1 Runtime Topology (Development)

```mermaid
graph TB
    subgraph Dev["Development Environment (Docker Compose)"]
        FE_DEV[Frontend Dev Server\nNext.js :3000]
        API_DEV[Backend API\nFastAPI :8000]
        WORKER_DEV[Celery Worker\n×2 concurrency]
        BEAT_DEV[Celery Beat\nScheduler]
        PG_DEV[(PostgreSQL + PostGIS\n:5432)]
        REDIS_DEV[(Redis\n:6379)]
        OSM_DEV[(OSM PostGIS\n:5433)]
    end

    FE_DEV --> API_DEV
    API_DEV --> PG_DEV
    API_DEV --> REDIS_DEV
    WORKER_DEV --> PG_DEV
    WORKER_DEV --> REDIS_DEV
    WORKER_DEV --> OSM_DEV
    BEAT_DEV --> REDIS_DEV
```

### 4.2 Runtime Topology (Production – Kubernetes)

```mermaid
graph TB
    subgraph K8s["Kubernetes Cluster"]
        subgraph Ingress["Ingress Layer"]
            NGINX[NGINX Ingress\nTLS Termination]
        end

        subgraph Frontend["Frontend Deployment"]
            FE_POD[Next.js Pods\nHPA: CPU>70% → scale]
        end

        subgraph Backend["Backend Deployment"]
            API_POD[FastAPI Pods\nHPA: RPS>100 → scale]
        end

        subgraph Workers["Worker Deployment"]
            WORKER_POD[Celery Worker Pods\nHPA: Queue depth>50 → scale\nMax: 20 pods]
            BEAT_POD[Celery Beat\nSingleton]
        end

        subgraph Data["Data Layer"]
            PG_PRIMARY[(PostgreSQL Primary\nManaged PG)]
            PG_REPLICA[(PostgreSQL Replica\nRead queries)]
            REDIS_CLUSTER[(Redis Cluster\n3 shards)]
            OSM_PG[(OSM PostGIS\nSeparate instance)]
        end

        subgraph Storage["Object Storage"]
            S3[S3-compatible\nFile uploads/exports]
        end

        subgraph Monitoring["Observability"]
            PROM[Prometheus]
            GRAF[Grafana]
            LOKI[Loki]
            TEMPO[Tempo]
        end
    end

    USER[Users] --> NGINX
    NGINX --> FE_POD
    NGINX --> API_POD
    FE_POD --> API_POD
    API_POD --> PG_PRIMARY
    API_POD --> REDIS_CLUSTER
    WORKER_POD --> PG_PRIMARY
    WORKER_POD --> REDIS_CLUSTER
    WORKER_POD --> OSM_PG
    WORKER_POD --> S3
    BEAT_POD --> REDIS_CLUSTER
    API_POD --> PROM
    WORKER_POD --> PROM
    PROM --> GRAF
    API_POD --> LOKI
    WORKER_POD --> LOKI
    API_POD --> TEMPO
    WORKER_POD --> TEMPO
```

### 4.3 Network Policies

| Policy | Source | Destination | Port | Protocol |
|--------|--------|-------------|------|----------|
| `frontend-to-api` | Frontend pods | API pods | 8000 | TCP |
| `api-to-db` | API pods | PostgreSQL | 5432 | TCP |
| `api-to-redis` | API pods | Redis | 6379 | TCP |
| `worker-to-db` | Worker pods | PostgreSQL | 5432 | TCP |
| `worker-to-redis` | Worker pods | Redis | 6379 | TCP |
| `worker-to-osm` | Worker pods | OSM PostGIS | 5432 | TCP |
| `worker-to-s3` | Worker pods | S3 endpoint | 443 | HTTPS |
| `monitoring-scrape` | Prometheus | All pods | 9090, 9100 | TCP |

---

## 5. Deployment Architecture

### 5.1 Docker Compose (Development)

```yaml
# docker-compose.yml – key services only
services:
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile.dev
    ports: ["3000:3000"]
    volumes:
      - ./frontend:/app
      - /app/node_modules
    environment:
      - NEXT_PUBLIC_API_URL=http://localhost:8000

  api:
    build:
      context: ./backend
      dockerfile: Dockerfile.dev
    ports: ["8000:8000"]
    volumes:
      - ./backend:/app
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/geocare
      - REDIS_URL=redis://redis:6379/0
      - OSM_DATABASE_URL=postgresql+asyncpg://postgres:postgres@osm-db:5432/osm
    depends_on: [db, redis, osm-db]

  worker:
    build:
      context: ./backend
      dockerfile: Dockerfile.dev
    command: celery -A geocare.infrastructure.queue.celery_app worker -l info -c 4
    volumes:
      - ./backend:/app
      - geography-data:/data/geography
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/geocare
      - REDIS_URL=redis://redis:6379/0
      - OSM_DATABASE_URL=postgresql+asyncpg://postgres:postgres@osm-db:5432/osm
      - GEOGRAPHY_DATA_PATH=/data/geography
    depends_on: [db, redis, osm-db]
    deploy:
      resources:
        limits:
          memory: 4G
          cpus: '2'

  beat:
    build:
      context: ./backend
      dockerfile: Dockerfile.dev
    command: celery -A geocare.infrastructure.queue.celery_app beat -l info
    volumes:
      - ./backend:/app
    environment:
      - REDIS_URL=redis://redis:6379/0
    depends_on: [redis]

  db:
    image: postgis/postgis:16-3.4
    environment:
      - POSTGRES_DB=geocare
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=postgres
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports: ["5432:5432"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s

  osm-db:
    image: postgis/postgis:16-3.4
    environment:
      - POSTGRES_DB=osm
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=postgres
    volumes:
      - osmdata:/var/lib/postgresql/data
    ports: ["5433:5432"]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s

volumes:
  pgdata:
  osmdata:
  redisdata:
  geography-data:
```

### 5.2 Production Deployment (Kubernetes)

| Component | Strategy | Resources |
|-----------|----------|-----------|
| **Frontend** | Rolling update, HPA (CPU) | 2–10 pods, 512Mi/1Gi |
| **API** | Rolling update, HPA (RPS) | 3–20 pods, 1Gi/2Gi |
| **Workers** | KEDA scaled on queue depth | 2–30 pods, 2Gi/4Gi |
| **Beat** | Singleton (leader election) | 1 pod, 256Mi/512Mi |
| **PostgreSQL** | Managed (Cloud SQL / RDS) | db.r6g.xlarge+ |
| **Redis** | ElastiCache Cluster Mode | 3 shards, r6g.large |
| **OSM PostGIS** | Dedicated instance | db.r6g.large |
| **Object Storage** | S3 / MinIO | Versioned bucket |

### 5.3 Geography Data Pipeline (Offline Refresh)

```mermaid
flowchart TD
    SCHEDULE[Quarterly Cron] --> DOWNLOAD[Download Datasets]
    DOWNLOAD --> INDIA_POST[India Post PIN CSV]
    DOWNLOAD --> OSM_PBF[OSM India PBF\ngeofabrik.de]
    DOWNLOAD --> CENSUS[Census Village/Town CSV]
    
    INDIA_POST --> VALIDATE[Validate Checksums\nRow Counts]
    OSM_PBF --> VALIDATE
    CENSUS --> VALIDATE
    
    VALIDATE --> LOAD_PIN[Load PIN to PostgreSQL\nCOPY + Indexes]
    VALIDATE --> LOAD_CENSUS[Load Census Hierarchy\nCOPY + Indexes]
    VALIDATE --> IMPORT_OSM[osm2pgsql → OSM PostGIS\nSlim mode, flat-nodes]
    
    LOAD_PIN --> BUILD_INDEX[Build In-Memory Indexes\nPIN→Locality, Fuzzy Dict]
    LOAD_CENSUS --> BUILD_INDEX
    IMPORT_OSM --> BUILD_INDEX
    
    BUILD_INDEX --> WARM_CACHE[Warm Redis Fuzzy Cache]
    WARM_CACHE --> VERIFY[Smoke Tests\nSample Queries]
    VERIFY --> PROMOTE[Swap Active Dataset Version]
    PROMOTE --> NOTIFY[Alert On Success/Failure]
```

### 5.4 Environment Configuration

| Variable | Dev | Prod | Description |
|----------|-----|------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://...` | Managed PG URI | Primary DB |
| `OSM_DATABASE_URL` | `postgresql+asyncpg://...` | Managed PG URI | OSM PostGIS |
| `REDIS_URL` | `redis://redis:6379/0` | ElastiCache cluster | Broker + cache |
| `GEOGRAPHY_DATA_PATH` | `/data/geography` | `/mnt/geography` | Downloaded datasets |
| `CELERY_CONCURRENCY` | `4` | `8` | Worker processes |
| `CHUNK_SIZE` | `10000` | `50000` | Rows per batch |
| `FUZZY_THRESHOLD` | `85` | `85` | RapidFuzz minimum score |
| `MAX_FILE_SIZE_MB` | `2048` | `2048` | Upload limit |
| `JWT_SECRET` | dev-secret | KMS-managed | Auth signing |
| `LOG_LEVEL` | `DEBUG` | `INFO` | Structured logging |

---

## 6. Clean Architecture Layers

### 6.1 Layer Responsibilities

```
┌─────────────────────────────────────────────────────────────┐
│                    PRESENTATION LAYER                        │
│  Next.js Frontend  │  FastAPI Routers  │  WebSocket Handler │
│  - HTTP Controllers                                                      │
│  - Request/Response Validation (Pydantic)                               │
│  - Serialization                                                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ (depends on interfaces)
┌─────────────────────────────────────────────────────────────┐
│                    APPLICATION LAYER                         │
│  Use Cases / Interactors  │  DTOs / Commands / Queries       │
│  - Orchestrate domain logic                                           │
│  - Transaction boundaries                                             │
│  - Port implementations (call infrastructure)                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ (depends on interfaces)
┌─────────────────────────────────────────────────────────────┐
│                      DOMAIN LAYER                            │
│  Entities  │  Value Objects  │  Domain Events  │  Interfaces │
│  - Business rules                                                     │
│  - Invariants                                                        │
│  - Pure Python, no external deps                                     │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │ (implements interfaces)
┌─────────────────────────────────────────────────────────────┐
│                  INFRASTRUCTURE LAYER                        │
│  Repositories  │  Geography Engine  │  Queue  │  Adapters   │
│  - SQLAlchemy impl of Repository interfaces                    │
│  - libpostal / RapidFuzz / PostGIS adapters                    │
│  - Celery task definitions                                     │
│  - File storage (S3/local)                                     │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 Dependency Rule Enforcement

- **Domain** → zero external imports (only `typing`, `dataclasses`, `datetime`, `uuid`)
- **Application** → imports `domain` only
- **Infrastructure** → imports `domain`, `application`
- **Presentation** → imports `application`, `domain` (DTOs)
- **Enforced by**: `import-linter` in CI (`python -m import_linter`)

### 6.3 Key Domain Interfaces (Ports)

```python
# geocare/domain/ports/repositories.py
from abc import ABC, abstractmethod
from geocare.domain.entities import ProcessingJob, PatientRecord, AuditEntry

class JobRepository(ABC):
    @abstractmethod
    async def create(self, job: ProcessingJob) -> ProcessingJob: ...
    @abstractmethod
    async def get(self, job_id: UUID) -> ProcessingJob | None: ...
    @abstractmethod
    async def update(self, job: ProcessingJob) -> ProcessingJob: ...
    @abstractmethod
    async def list_by_user(self, user_id: UUID, limit: int, offset: int) -> list[ProcessingJob]: ...

class RecordRepository(ABC):
    @abstractmethod
    async def bulk_create(self, records: list[PatientRecord]) -> list[PatientRecord]: ...
    @abstractmethod
    async def get_batch(self, job_id: UUID, offset: int, limit: int) -> list[PatientRecord]: ...
    @abstractmethod
    async def update_enriched(self, record: PatientRecord) -> PatientRecord: ...
    @abstractmethod
    async def count_by_status(self, job_id: UUID) -> dict[ReviewStatus, int]: ...

class AuditRepository(ABC):
    @abstractmethod
    async def bulk_create(self, entries: list[AuditEntry]) -> None: ...
    @abstractmethod
    async def get_for_record(self, record_id: UUID) -> list[AuditEntry]: ...

# geocare/domain/ports/geography.py
class GeographyEngine(ABC):
    @abstractmethod
    async def resolve_pincode(self, pincode: str) -> PincodeResolution | None: ...
    @abstractmethod
    async def match_locality(self, name: str, context: GeoContext) -> LocalityMatch | None: ...
    @abstractmethod
    async def enrich_from_pincode(self, pincode: str) -> EnrichmentResult | None: ...
    @abstractmethod
    async def parse_address(self, text: str) -> ParsedAddress: ...
    @abstractmethod
    async def validate_geography(self, enriched: EnrichedAddress) -> ValidationResult: ...
```

---

## 7. Component Architecture

### 7.1 Backend Component Diagram

```mermaid
C4Component
    title Component Diagram – Backend (geocare)

    Container_Boundary(api, "FastAPI Application") {
        Component(auth_router, "Auth Router", "FastAPI", "Login, register, JWT")
        Component(upload_router, "Upload Router", "FastAPI", "File upload, column mapping")
        Component(job_router, "Job Router", "FastAPI", "Job CRUD, progress, results")
        Component(report_router, "Report Router", "FastAPI", "Quality reports, export")
        Component(admin_router, "Admin Router", "FastAPI", "User mgmt, geo refresh")
        Component(ws_handler, "WebSocket Handler", "FastAPI", "Real-time job progress")
    }

    Container_Boundary(app, "Application Layer") {
        Component(upload_uc, "Upload Use Case", "Python", "Validate, profile, create job")
        Component(process_uc, "Process Use Case", "Python", "Enqueue batches, monitor")
        Component(report_uc, "Report Use Case", "Python", "Generate before/after reports")
        Component(export_uc, "Export Use Case", "Python", "Stream CSV/Excel/Parquet")
        Component(geo_refresh_uc, "Geography Refresh UC", "Python", "Orchestrate data reload")
    }

    Container_Boundary(domain, "Domain Layer") {
        Component(job_entity, "ProcessingJob", "Entity", "Job lifecycle, status machine")
        Component(record_entity, "PatientRecord", "Entity", "Record state, enrichment")
        Component(confidence_vo, "ConfidenceScore", "Value Object", "Scoring logic, tiers")
        Component(audit_vo, "AuditEntry", "Value Object", "Immutable transformation log")
        Component(geo_entities, "Geography Entities", "Entity", "Pincode, Locality, City...")
    }

    Container_Boundary(infra, "Infrastructure Layer") {
        Component(sql_repo, "SQLAlchemy Repos", "SQLAlchemy", "Job/Record/Audit persistence")
        Component(geo_engine, "Geography Engine", "Polars/RapidFuzz/libpostal", "Core enrichment logic")
        Component(celery_tasks, "Celery Tasks", "Celery", "Batch processing workers")
        Component(parser_adapter, "libpostal Adapter", "postal", "Address parsing")
        Component(fuzzy_adapter, "RapidFuzz Adapter", "RapidFuzz", "Fuzzy matching")
        Component(postgis_loader, "PostGIS Loader", "GeoPandas/osm2pgsql", "OSM boundary load")
        Component(file_storage, "File Storage", "S3/Local", "Upload/export files")
    }

    Rel(auth_router, upload_uc, "Calls")
    Rel(upload_router, upload_uc, "Calls")
    Rel(job_router, process_uc, "Calls")
    Rel(report_router, report_uc, "Calls")
    Rel(admin_router, geo_refresh_uc, "Calls")
    Rel(ws_handler, process_uc, "Subscribes")

    Rel(upload_uc, sql_repo, "Persists job")
    Rel(upload_uc, geo_engine, "Profiles columns")
    Rel(process_uc, celery_tasks, "Enqueues batches")
    Rel(process_uc, sql_repo, "Updates progress")
    Rel(report_uc, sql_repo, "Reads records")
    Rel(export_uc, sql_repo, "Streams records")
    Rel(export_uc, file_storage, "Writes export")
    Rel(geo_refresh_uc, postgis_loader, "Loads OSM")
    Rel(geo_refresh_uc, geo_engine, "Rebuilds indexes")

    Rel(celery_tasks, geo_engine, "Processes batch")
    Rel(celery_tasks, sql_repo, "Reads/writes records")
    Rel(celery_tasks, parser_adapter, "Parses addresses")
    Rel(celery_tasks, fuzzy_adapter, "Matches localities")
    Rel(geo_engine, sql_repo, "Loads reference data")
    Rel(geo_engine, fuzzy_adapter, "Fuzzy matches")
    Rel(parser_adapter, celery_tasks, "Called by")
```

### 7.2 Frontend Component Architecture

```mermaid
graph TB
    subgraph App["Next.js App Router"]
        Layout[Root Layout\nProviders: Auth, Theme, Query]
        
        subgraph Pages["Pages"]
            Login[/login]
            Dashboard[/dashboard]
            Upload[/upload]
            JobDetail[/jobs/[id]]
            Reports[/reports/[id]]
            Admin[/admin/*]
        end
        
        subgraph Components["Shared Components"]
            UI[shadcn/ui Primitives\nButton, Table, Dialog...]
            Charts[ECharts Wrapper\nBar, Line, Heatmap, Sankey]
            Forms[React Hook Form + Zod]
            Progress[Job Progress WebSocket]
        end
    end
    
    Layout --> Pages
    Pages --> Components
    Components --> UI
    Components --> Charts
    Components --> Forms
    JobDetail --> Progress
```

---

## 8. Processing Pipeline

### 8.1 End-to-End Flow

```mermaid
flowchart TD
    A[User Uploads File] --> B[Validate File Format]
    B --> C[Profile Dataset\nPolars: sample 10k rows]
    C --> D[Auto-Detect Address Columns\nHeader + Content Heuristics]
    D --> E[User Confirms Column Mapping]
    E --> F[Create ProcessingJob\nStatus: PROFILING]
    F --> G[Chunk File into Batches\nDefault: 50k rows]
    G --> H[Enqueue Batches to Celery]
    H --> I[Worker Picks Batch]
    I --> J[Process Batch Pipeline]
    J --> K{More Batches?}
    K -- Yes --> I
    K -- No --> L[All Batches Complete]
    L --> M[Generate Quality Report]
    M --> N[Update Job Status: COMPLETED]
    N --> O[WebSocket Notify Frontend]
    O --> P[User Downloads Results]
    
    subgraph Batch_Processing[Batch Processing Pipeline]
        J1[Load Batch from Storage]
        J2[Normalize Addresses\nUnicode, Abbreviations, Case]
        J3[Parse with libpostal\nStructured Components]
        J4[Fuzzy Match Localities\nRapidFuzz + Context]
        J5[Resolve PIN Codes\nIndia Post Index]
        J6[Enrich Hierarchy\nCity/District/State]
        J7[Validate Geography\nPostGIS Consistency]
        J8[Calculate Confidence\nWeighted Scoring]
        J9[Create Audit Entries\nImmutable Log]
        J10[Persist Enriched Records\nBulk Upsert]
        
        J1 --> J2 --> J3 --> J4 --> J5 --> J6 --> J7 --> J8 --> J9 --> J10
    end
    
    J -.-> J1
```

### 8.2 Batch Processing Details

| Stage | Input | Output | Library | Parallelism |
|-------|-------|--------|---------|-------------|
| **Load** | Parquet chunk (S3/local) | Polars DataFrame | Polars | 1 per worker |
| **Normalize** | Raw address strings | Normalized strings | Custom + RapidFuzz | Vectorized |
| **Parse** | Normalized address | ParsedAddress components | libpostal (`postal`) | Per-row |
| **Fuzzy Match** | Parsed locality + context | LocalityMatch (canonical, score) | RapidFuzz + BK-Tree | Vectorized + cached |
| **PIN Resolve** | PIN string / inferred | PincodeResolution | In-memory dict | O(1) lookup |
| **Enrich** | Partial components | Full EnrichedAddress | Hierarchy dict + PostGIS | Vectorized |
| **Validate** | EnrichedAddress | ValidationResult (errors/warnings) | PostGIS + rules | Per-row |
| **Score** | All match results | ConfidenceScore (0-100, tier) | Custom weighted | Vectorized |
| **Audit** | Original → Enriched | List[AuditEntry] | Domain logic | Per-field |
| **Persist** | Enriched records | DB rows | SQLAlchemy bulk | Batch insert |

### 8.3 Chunking Strategy

```python
# geocare/application/use_cases/processing.py (conceptual)

CHUNK_SIZE = 50_000  # rows per batch
MAX_CHUNKS_IN_MEMORY = 3  # streaming buffer

async def chunk_file(file_path: Path, chunk_size: int) -> AsyncIterator[Batch]:
    """Stream file in chunks without loading entirely into memory."""
    if file_path.suffix == '.parquet':
        # Polars streaming read
        for batch in pl.scan_parquet(file_path).slice(chunk_size).collect().iter_slices(chunk_size):
            yield Batch(rows=batch.to_pylist())
    elif file_path.suffix in ('.csv', '.xlsx'):
        # Polars read_csv/read_excel with batch_size
        for batch in pl.read_csv_batched(file_path, batch_size=chunk_size):
            yield Batch(rows=batch.to_pylist())
```

### 8.4 Checkpointing & Resume

```mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> PROFILING: User uploads
    PROFILING --> MAPPING: Profile complete
    MAPPING --> QUEUED: User confirms mapping
    QUEUED --> PROCESSING: Worker starts
    PROCESSING --> PROCESSING: Batch complete
    PROCESSING --> COMPLETED: All batches done
    PROCESSING --> FAILED: Error (max retries)
    FAILED --> QUEUED: User retries
    COMPLETED --> [*]
    FAILED --> [*]
    
    note right of PROCESSING
        Checkpoint: completed_chunk_ids[]
        Resume: skip completed chunks
    end note
```

| Checkpoint Data | Storage | Recovery Action |
|-----------------|---------|-----------------|
| `completed_chunk_ids` | Job table (JSONB) | Skip processed chunks |
| `failed_chunk_ids` | Job table (JSONB) | Retry failed chunks |
| `last_processed_row` | Redis (job:{id}:progress) | Resume from offset |
| `worker_heartbeat` | Redis (worker:{id}:alive) | Detect stale workers |

### 8.5 Progress Tracking

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant API as FastAPI
    participant Redis as Redis
    participant Worker as Celery Worker
    
    FE->>API: POST /jobs (create)
    API->>Redis: Set job:{id}:status=QUEUED
    API-->>FE: job_id
    
    loop Per Batch
        Worker->>Redis: BRPOP queue:job:{id}
        Worker->>Redis: INCR job:{id}:processed
        Worker->>Redis: SET job:{id}:current_batch={n}
        Worker->>API: PATCH /jobs/{id}/progress (batch done)
        API->>Redis: HSET job:{id} progress=X%
    end
    
    FE->>API: GET /jobs/{id}/stream (SSE)
    API->>Redis: SUBSCRIBE job:{id}:progress
    Redis-->>API: Progress updates
    API-->>FE: Server-Sent Events
    
    Worker->>Redis: SET job:{id}:status=COMPLETED
    API-->>FE: Final status via SSE
```

---

## 9. Geography Intelligence Engine

### 9.1 Overview

The Geography Intelligence Engine is the core enrichment component. It combines multiple open-source datasets to resolve Indian addresses with confidence scoring. All data is pre-loaded into memory/Redis at startup — zero external calls during processing.

```mermaid
C4Component
    title Component Diagram – Geography Intelligence Engine

    Container_Boundary(engine, "Geography Engine") {
        Component(pindex, "PIN Code Index", "Python dict + Redis", "19k PINs → O(1) lookup")
        Component(flocal, "Locality Fuzzy Index", "BK-Tree + Trie + RapidFuzz", "1.5M localities, fuzzy match")
        Component(chier, "Census Hierarchy", "Nested dict + PostGIS", "State→District→Taluk→Village")
        Component(parser, "libpostal Adapter", "postal (C binding)", "Address parsing")
        Component(validate, "Geography Validator", "PostGIS + Rules", "Consistency checks")
        Component(enrich, "Enrichment Orchestrator", "Python", "Coordinates all lookups")
    }

    Container_Boundary(data, "Reference Data (PostgreSQL)") {
        ComponentDb(pin_tbl, "pincode_directory", "Table", "India Post official")
        ComponentDb(loc_tbl, "locality_dictionary", "Table", "India Post + OSM + Census")
        ComponentDb(cen_tbl, "census_hierarchy", "Table", "Census 2011/2021")
        ComponentDb(osm_tbl, "osm_boundaries", "PostGIS", "Admin polygons")
    }

    Rel(enrich, pindex, "Resolve PIN")
    Rel(enrich, flocal, "Match Locality")
    Rel(enrich, chier, "Enrich Hierarchy")
    Rel(enrich, parser, "Parse Address")
    Rel(enrich, validate, "Validate Result")
    
    Rel(pindex, pin_tbl, "Load at startup")
    Rel(flocal, loc_tbl, "Load at startup")
    Rel(chier, cen_tbl, "Load at startup")
    Rel(validate, osm_tbl, "Spatial queries")
```

### 9.2 PIN Code Index

```python
# geocare/infrastructure/geography/pincode_index.py (conceptual)

class PincodeIndex:
    """In-memory PIN code index with O(1) lookup."""
    
    def __init__(self):
        self.by_code: dict[str, PincodeRecord] = {}  # "500081" -> record
        self.by_locality: dict[str, list[str]] = defaultdict(list)  # "madhapur" -> ["500081", "500082"]
        self.by_district_state: dict[tuple[str, str], list[str]] = defaultdict(list)
    
    def load(self, df: pl.DataFrame) -> None:
        """Build indexes from Polars DataFrame."""
        for row in df.iter_rows(named=True):
            code = row['pincode']
            self.by_code[code] = PincodeRecord(**row)
            # Reverse index: locality -> PINs
            for loc in row['localities'].split(','):
                self.by_locality[loc.strip().lower()].append(code)
            self.by_district_state[(row['district'], row['state'])].append(code)
    
    def resolve(self, pincode: str) -> PincodeResolution | None:
        """Exact PIN lookup with validation."""
        if not PIN_REGEX.match(pincode):
            return None
        record = self.by_code.get(pincode)
        if not record:
            return None
        return PincodeResolution(
            pincode=record.code,
            district=record.district,
            state=record.state,
            taluk=record.taluk,
            latitude=record.latitude,
            longitude=record.longitude,
            confidence=100,
            source=DataSource.INDIA_POST
        )
    
    def reverse_lookup(self, locality: str, district: str | None, state: str | None) -> list[PincodeResolution]:
        """Find candidate PINs for a locality (with optional context)."""
        candidates = self.by_locality.get(locality.lower(), [])
        if district and state:
            candidates = [c for c in candidates if c in self.by_district_state[(district, state)]]
        return [self.resolve(c) for c in candidates if self.resolve(c)]
```

| Metric | Target |
|--------|--------|
| **Index Size** | ~19,000 PIN codes, ~150,000 locality→PIN mappings |
| **Memory Footprint** | < 50 MB |
| **Lookup Latency** | < 1 ms (in-memory dict) |
| **Build Time** | < 5 seconds (Polars → dict) |

### 9.3 Locality Fuzzy Index

```mermaid
flowchart TD
    QUERY[Input Locality String] --> EXACT{Exact Match?}
    EXACT -- Yes --> RETURN[Return Canonical\nConfidence: 100]
    EXACT -- No --> PREFIX{Prefix Match?}
    PREFIX -- Yes --> CANDIDATES[Candidate Set\nTrie Prefix]
    PREFIX -- No --> FUZZY[BK-Tree Levenshtein < 3\n+ RapidFuzz Token-Set]
    
    CANDIDATES --> RANK[Rank by:\n1. Exact > Prefix > Fuzzy\n2. Context Score (PIN/District/State)\n3. Population Weight]
    FUZZY --> RANK
    RANK --> FILTER[Filter Threshold ≥ 85]
    FILTER --> TOP[Top-K Results]
    TOP --> CONTEXT{Context Match?}
    CONTEXT -- Yes --> BOOST[Boost Score]
    CONTEXT -- No --> KEEP
    BOOST --> FINAL[Final Ranked List]
    KEEP --> FINAL
```

```python
# geocare/infrastructure/geography/locality_fuzzy.py (conceptual)

class LocalityFuzzyIndex:
    """Multi-strategy locality matching with context awareness."""
    
    def __init__(self, threshold: int = 85):
        self.threshold = threshold
        self.trie = Trie()  # Prefix matching
        self.bk_tree = BKTree()  # Levenshtein distance
        self.canonical: dict[str, LocalityRecord] = {}  # canonical_name -> record
        self.aliases: dict[str, str] = {}  # alias -> canonical_name
        self.redis_cache = RedisFuzzyCache()
    
    def load(self, df: pl.DataFrame) -> None:
        for row in df.iter_rows(named=True):
            canon = row['canonical_name']
            self.canonical[canon] = LocalityRecord(**row)
            self.trie.insert(canon.lower())
            self.bk_tree.add(canon.lower())
            for alias in row['aliases']:
                self.aliases[alias.lower()] = canon
    
    async def match(self, query: str, context: GeoContext) -> list[LocalityMatch]:
        # Check Redis cache first
        cache_key = f"fuzzy:{hash(query + str(context))}"
        cached = await self.redis_cache.get(cache_key)
        if cached:
            return cached
        
        # Multi-strategy search
        candidates = set()
        
        # 1. Exact alias match
        if query.lower() in self.aliases:
            candidates.add(self.aliases[query.lower()])
        
        # 2. Prefix match (Trie)
        candidates.update(self.trie.prefix_search(query.lower()))
        
        # 3. Fuzzy match (BK-Tree + RapidFuzz)
        bk_candidates = self.bk_tree.search(query.lower(), max_dist=2)
        rf_candidates = rapidfuzz.process.extract(
            query, self.canonical.keys(), 
            scorer=rapidfuzz.fuzz.token_set_ratio,
            score_cutoff=self.threshold,
            limit=50
        )
        candidates.update(bk_candidates)
        candidates.update([c for c, s, _ in rf_candidates])
        
        # Rank with context
        results = []
        for canon in candidates:
            record = self.canonical[canon]
            score = self._calculate_score(query, record, context)
            if score >= self.threshold:
                results.append(LocalityMatch(
                    canonical_name=record.canonical_name,
                    pincode=record.pincode,
                    city=record.city,
                    district=record.district,
                    state=record.state,
                    score=score,
                    method=self._determine_method(query, record),
                    source=record.source
                ))
        
        results.sort(key=lambda x: x.score, reverse=True)
        await self.redis_cache.set(cache_key, results[:10], ttl=86400)
        return results[:10]
    
    def _calculate_score(self, query: str, record: LocalityRecord, context: GeoContext) -> int:
        base = rapidfuzz.fuzz.token_set_ratio(query.lower(), record.canonical_name.lower())
        
        # Context boost
        if context.pincode and context.pincode in record.pincodes:
            base = min(100, base + 15)
        if context.district and context.district.lower() == record.district.lower():
            base = min(100, base + 10)
        if context.state and context.state.lower() == record.state.lower():
            base = min(100, base + 5)
        
        # Population weight (if available)
        if record.population:
            base = min(100, base + min(5, record.population // 100000))
        
        return base
```

| Metric | Target |
|--------|--------|
| **Dictionary Size** | ~1.5M unique localities (India Post + OSM + Census) |
| **Memory Footprint** | ~500 MB (Trie + BK-Tree + Records) |
| **Match Latency (cached)** | < 5 ms |
| **Match Latency (cold)** | < 50 ms |
| **Cache Hit Rate** | > 80% after warmup |

### 9.4 Census Hierarchy Engine

```python
# geocare/infrastructure/geography/census_hierarchy.py (conceptual)

class CensusHierarchy:
    """State → District → Sub-district → Village/Town hierarchy."""
    
    def __init__(self):
        self.states: dict[str, StateNode] = {}  # code -> StateNode
        self.by_name: dict[str, list[HierarchyNode]] = defaultdict(list)  # fuzzy lookup
    
    def load(self, df: pl.DataFrame) -> None:
        # Build tree from Census codes
        for row in df.iter_rows(named=True):
            state_code = row['state_code']
            district_code = row['district_code']
            subdistrict_code = row['subdistrict_code']
            village_code = row['village_code']
            
            state = self.states.setdefault(state_code, StateNode(code=state_code, name=row['state_name']))
            district = state.districts.setdefault(district_code, DistrictNode(code=district_code, name=row['district_name']))
            subdistrict = district.subdistricts.setdefault(subdistrict_code, SubdistrictNode(code=subdistrict_code, name=row['subdistrict_name']))
            subdistrict.villages[village_code] = VillageNode(code=village_code, name=row['village_name'], level=row['level'])
            
            # Name index for fuzzy lookup
            self.by_name[row['state_name'].lower()].append(state)
            self.by_name[row['district_name'].lower()].append(district)
            self.by_name[row['subdistrict_name'].lower()].append(subdistrict)
            self.by_name[row['village_name'].lower()].append(subdistrict.villages[village_code])
    
    def enrich_from_pincode(self, pincode: str) -> EnrichmentResult | None:
        """Use PIN → (District, State) to walk hierarchy up/down."""
        pin_record = self.pindex.resolve(pincode)
        if not pin_record:
            return None
        
        state = self.states.get(pin_record.state_code)
        if not state:
            return None
        
        district = state.districts.get(pin_record.district_code)
        # Find city/town from district (level 8 in Census)
        cities = [v for v in district.all_villages() if v.level in ('Town', 'City')]
        
        return EnrichmentResult(
            state=state.name,
            district=district.name,
            cities=[c.name for c in cities],
            taluk=pin_record.taluk,
            confidence=95
        )
```

### 9.5 libpostal Integration

```python
# geocare/infrastructure/geography/parser_adapter.py (conceptual)

class LibpostalAdapter:
    """Wrapper around postal.parser with India-specific enhancements."""
    
    def __init__(self, libpostal_data_dir: str):
        os.environ['LIBPOSTAL_DATA_DIR'] = libpostal_data_dir
        import postal.parser
        self.parser = postal.parser
    
    def parse(self, address: str) -> ParsedAddress:
        # Pre-process: expand known Indian abbreviations
        expanded = self._expand_indian_abbreviations(address)
        
        # Parse with libpostal
        parsed = self.parser.parse_address(expanded)
        
        # Map libpostal labels to our domain model
        components = {label: value for value, label in parsed}
        
        return ParsedAddress(
            house_number=components.get('house_number') or components.get('house'),
            street=components.get('road') or components.get('street'),
            locality=components.get('suburb') or components.get('neighbourhood'),
            sublocality=components.get('suburb'),
            village=components.get('village'),
            city=components.get('city') or components.get('town'),
            district=components.get('state_district') or components.get('district'),
            state=components.get('state'),
            pincode=self._extract_pincode(address),  # Custom PIN extraction
            country="India"
        )
    
    def _expand_indian_abbreviations(self, text: str) -> str:
        """Expand common Indian address abbreviations before parsing."""
        abbrevs = {
            r'\bRd\b': 'Road', r'\bSt\b': 'Street', r'\bAve\b': 'Avenue',
            r'\bNgr\b': 'Nagar', r'\bClny\b': 'Colony', r'\bExtn\b': 'Extension',
            r'\bSec\b': 'Sector', r'\bBlk\b': 'Block', r'\bPh\b': 'Phase',
            r'\bAppt\b': 'Apartment', r'\bFlr\b': 'Floor', r'\bBldg\b': 'Building',
            r'\bNr\b': 'Near', r'\bOpp\b': 'Opposite', r'\bB/h\b': 'Behind'
        }
        for pattern, replacement in abbrevs.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text
    
    def _extract_pincode(self, text: str) -> str | None:
        """Extract 6-digit PIN from anywhere in address."""
        matches = re.findall(r'\b[1-8]\d{5}\b', text)
        return matches[-1] if matches else None  # Last PIN in text (usually at end)
```

### 9.6 PostGIS Boundary Integration

```sql
-- OSM Admin Boundaries Schema (loaded via osm2pgsql)
CREATE TABLE osm_admin_boundaries (
    id BIGSERIAL PRIMARY KEY,
    osm_id BIGINT NOT NULL,
    admin_level SMALLINT NOT NULL,  -- 4=state, 6=district, 8=city, 10=village
    name TEXT NOT NULL,
    name_en TEXT,
    name_hi TEXT,  -- Devanagari
    tags JSONB,
    geom GEOMETRY(MULTIPOLYGON, 4326) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_osm_admin_level ON osm_admin_boundaries(admin_level);
CREATE INDEX idx_osm_name ON osm_admin_boundaries(name);
CREATE INDEX idx_osm_geom ON osm_admin_boundaries USING GIST(geom);

-- Materialized views for choropleth
CREATE MATERIALIZED VIEW state_choropleth AS
SELECT osm_id, name, name_en, geom
FROM osm_admin_boundaries
WHERE admin_level = 4;

CREATE MATERIALIZED VIEW district_choropleth AS
SELECT osm_id, name, name_en, geom
FROM osm_admin_boundaries
WHERE admin_level = 6;
```

```python
# geocare/infrastructure/geography/postgis_repo.py (conceptual)

class PostGISRepository:
    """Spatial queries for validation and choropleth."""
    
    async def validate_hierarchy(self, enriched: EnrichedAddress) -> ValidationResult:
        """Check if City ⊂ District ⊂ State spatially."""
        # Point-in-polygon: locality centroid within district within state
        point = f"POINT({enriched.longitude} {enriched.latitude})"
        
        query = """
            SELECT 
                city.name as city_name,
                dist.name as district_name,
                state.name as state_name
            FROM osm_admin_boundaries city
            JOIN osm_admin_boundaries dist 
                ON ST_Contains(dist.geom, city.geom) AND dist.admin_level = 6
            JOIN osm_admin_boundaries state 
                ON ST_Contains(state.geom, dist.geom) AND state.admin_level = 4
            WHERE city.admin_level = 8
            AND ST_Contains(city.geom, ST_GeomFromText($1, 4326))
        """
        result = await self.db.fetchrow(query, point)
        
        if not result:
            return ValidationResult(valid=False, errors=["No containing hierarchy found"])
        
        errors = []
        if enriched.city.lower() != result['city_name'].lower():
            errors.append(f"City mismatch: {enriched.city} vs {result['city_name']}")
        if enriched.district.lower() != result['district_name'].lower():
            errors.append(f"District mismatch: {enriched.district} vs {result['district_name']}")
        if enriched.state.lower() != result['state_name'].lower():
            errors.append(f"State mismatch: {enriched.state} vs {result['state_name']}")
        
        return ValidationResult(valid=len(errors)==0, errors=errors)
    
    async def get_choropleth_data(self, level: str, job_id: UUID) -> list[dict]:
        """Aggregate record counts by boundary for heatmap."""
        view = {"state": "state_choropleth", "district": "district_choropleth"}[level]
        
        query = f"""
            SELECT b.name, b.name_en, b.geom, COUNT(r.id) as record_count
            FROM {view} b
            JOIN patient_records r ON ST_Contains(b.geom, ST_Point(r.longitude, r.latitude))
            WHERE r.job_id = $1
            GROUP BY b.osm_id, b.name, b.name_en, b.geom
        """
        return await self.db.fetch(query, job_id)
```

---

## 10. Address Intelligence Engine

### 10.1 Pipeline Stages

```mermaid
flowchart LR
    subgraph Normalization["1. Normalization"]
        N1[Unicode NFC]
        N2[Trim/Collapse Whitespace]
        N3[Expand Abbreviations]
        N4[Title Case Proper Nouns]
        N5[Remove Noise Tokens]
    end
    
    subgraph Parsing["2. Parsing (libpostal)"]
        P1[Structured Components]
        P2[PIN Extraction]
        P3[Component Mapping]
    end
    
    subgraph Correction["3. Spelling Correction"]
        C1[Fuzzy Match Locality]
        C2[Fuzzy Match City]
        C3[Fuzzy Match District]
        C4[Fuzzy Match State]
        C5[Transliteration Variants]
    end
    
    subgraph Resolution["4. Resolution"]
        R1[PIN → District/State]
        R2[Locality → PIN]
        R3[Hierarchy Completion]
        R4[Cross-Validation]
    end
    
    subgraph Formatting["5. Standardization"]
        F1[Canonical Format]
        F2[Formatted Address String]
        F3[Component Separation]
    end
    
    N1 --> N2 --> N3 --> N4 --> N5 --> P1 --> P2 --> P3 --> C1 --> C2 --> C3 --> C4 --> C5 --> R1 --> R2 --> R3 --> R4 --> F1 --> F2 --> F3
```

### 10.2 Normalization Rules

| Rule | Pattern | Replacement | Example |
|------|---------|-------------|---------|
| Unicode NFC | – | – | `नगर` (composed) |
| Whitespace | `\s+` | ` ` | `"Madhapur  Hyderabad"` → `"Madhapur Hyderabad"` |
| Abbreviation: Road | `\bRd\b` | `Road` | `"MG Rd"` → `"MG Road"` |
| Abbreviation: Street | `\bSt\b` | `Street` | `"1st St"` → `"1st Street"` |
| Abbreviation: Nagar | `\bNgr\b` | `Nagar` | `"Koramangala Ngr"` → `"Koramangala Nagar"` |
| Abbreviation: Colony | `\bClny\b` | `Colony` | `"Adarsh Clny"` → `"Adarsh Colony"` |
| Title Case | – | `str.title()` | `"madhapur"` → `"Madhapur"` |
| Noise Removal | `\b(Near|Opp|Behind|Beside|Near to|Opposite)\b` | `` | `"Near Metro Station"` → `"Metro Station"` |
| Preserve Numbers | – | – | `"Flat 404"` kept intact |

### 10.3 Parsing Output Mapping

```mermaid
graph TD
    LIBPOSTAL[libpostal Output\nList[(value, label)]] --> MAP[Label Mapping]
    
    MAP --> HOUSE[house_number, house\n→ house_number]
    MAP --> STREET[road, street\n→ street]
    MAP --> LOCALITY[suburb, neighbourhood\n→ locality]
    MAP --> SUBLOC[suburb\n→ sublocality]
    MAP --> VILLAGE[village\n→ village]
    MAP --> CITY[city, town\n→ city]
    MAP --> DISTRICT[state_district, district\n→ district]
    MAP --> STATE[state\n→ state]
    MAP --> PIN[postcode\n→ pincode]
    MAP --> COUNTRY[country\n→ country]
    
    PIN --> PINEXTRACT[Custom PIN Regex\nFallback if missing]
```

### 10.4 Spelling Correction Strategies

| Strategy | Scope | Method | Threshold |
|----------|-------|--------|-----------|
| **Locality** | 1.5M names | BK-Tree (Levenshtein ≤2) + RapidFuzz token_set_ratio | 85% |
| **City** | ~4,000 | RapidFuzz + Census hierarchy context | 90% |
| **District** | ~700 | RapidFuzz + State context | 90% |
| **State** | 36 | RapidFuzz (exact/near-exact) | 95% |
| **Transliteration** | Known variants | Hardcoded map + phonetic matching | N/A |

```python
# Transliteration variant map (sample)
TRANSLITERATION_VARIANTS = {
    "bangalore": "bengaluru",
    "bombay": "mumbai",
    "madras": "chennai",
    "calcutta": "kolkata",
    "trivandrum": "thiruvananthapuram",
    "pondicherry": "puducherry",
    "mysore": "mysuru",
    "mangalore": "mangaluru",
    "belgaum": "belagavi",
    "hubli": "hubballi",
    "gulbarga": "kalaburagi",
    "bellary": "ballari",
    "shimoga": "shivamogga",
    "tumkur": "tumakuru",
    "bijapur": "vijayapura",
    "chikmagalur": "chikkamagaluru"
}
```

### 10.5 Resolution Logic

```python
# geocare/infrastructure/geography/resolution.py (conceptual)

class AddressResolver:
    """Orchestrate multi-source resolution with fallback chain."""
    
    def __init__(
        self, 
        pincode_index: PincodeIndex,
        locality_fuzzy: LocalityFuzzyIndex,
        census_hierarchy: CensusHierarchy,
        postgis: PostGISRepository
    ):
        self.pincode = pincode_index
        self.locality = locality_fuzzy
        self.hierarchy = census_hierarchy
        self.postgis = postgis
    
    async def resolve(self, parsed: ParsedAddress) -> EnrichedAddress:
        context = GeoContext(
            pincode=parsed.pincode,
            city=parsed.city,
            district=parsed.district,
            state=parsed.state
        )
        
        # 1. PIN resolution (highest confidence)
        pincode_result = None
        if parsed.pincode:
            pincode_result = self.pincode.resolve(parsed.pincode)
            if pincode_result:
                context = context.merge(pincode_result.to_context())
        
        # 2. Locality resolution (with context)
        locality_result = None
        if parsed.locality:
            matches = await self.locality.match(parsed.locality, context)
            if matches:
                locality_result = matches[0]
                context = context.merge(locality_result.to_context())
        
        # 3. City/District/State resolution
        city_result = self._resolve_city(parsed.city, context)
        district_result = self._resolve_district(parsed.district, context)
        state_result = self._resolve_state(parsed.state, context)
        
        # 4. Cross-validate hierarchy
        enriched = EnrichedAddress(
            line1=parsed.house_number + " " + parsed.street if parsed.house_number else parsed.street,
            line2=parsed.sublocality,
            locality=locality_result.canonical_name if locality_result else parsed.locality,
            city=city_result or parsed.city,
            district=district_result or parsed.district,
            state=state_result or parsed.state,
            pincode=pincode_result.pincode if pincode_result else parsed.pincode,
            country="India"
        )
        
        # 5. PostGIS validation
        if enriched.latitude and enriched.longitude:
            validation = await self.postgis.validate_hierarchy(enriched)
            if not validation.valid:
                enriched = self._apply_corrections(enriched, validation)
        
        return enriched
    
    def _resolve_city(self, city: str | None, context: GeoContext) -> str | None:
        if city:
            matches = rapidfuzz.process.extract(
                city, self.hierarchy.all_cities(),
                scorer=rapidfuzz.fuzz.token_set_ratio,
                score_cutoff=90,
                limit=1
            )
            if matches:
                return matches[0][0]
        
        # Fallback: infer from PIN/district
        if context.district:
            district = self.hierarchy.get_district(context.district, context.state)
            if district:
                return district.main_city
        return None
```

---

## 11. Data Quality Engine

### 11.1 Pre-Processing Profiling

```mermaid
flowchart TD
    INPUT[Raw Dataset] --> SCHEMA[Infer Schema\nPolars scan]
    SCHEMA --> STATS[Column Statistics]
    
    STATS --> C1[Null % per column]
    STATS --> C2[Distinct Count]
    STATS --> C3[Min/Max Length]
    STATS --> C4[Pattern Regex]
    STATS --> C5[Sample Values]
    
    C1 --> DETECT[Address Column Detection]
    C2 --> DETECT
    C3 --> DETECT
    C4 --> DETECT
    C5 --> DETECT
    
    DETECT --> HEURISTIC[Header Keywords:\naddress, locality, pincode, city...]
    DETECT --> CONTENT[Content Patterns:\n6-digit PIN, known city names...]
    
    HEURISTIC --> SCORE[Column Address Score]
    CONTENT --> SCORE
    
    SCORE --> MAP[User Confirms/Adjusts Mapping]
    MAP --> BASELINE[Quality Baseline Report]
    
    BASELINE --> METRICS[Metrics:\n- Total Records\n- Complete Addresses\n- Missing PIN\n- Missing Locality\n- Missing City\n- Missing District\n- Missing State\n- Invalid Addresses\n- Duplicate Addresses\n- Overall Quality %]
```

### 11.2 Quality Metrics Definitions

| Metric | Formula | Threshold (Good) |
|--------|---------|------------------|
| **Completeness** | `(non_null_cells / total_cells) × 100` | ≥ 90% |
| **Address Completeness** | `(records_with_all_components / total_records) × 100` | ≥ 70% |
| **PIN Validity** | `(valid_pincodes / total_pincodes) × 100` | ≥ 95% |
| **Format Consistency** | `(records_matching_dominant_pattern / total) × 100` | ≥ 80% |
| **Duplicate Rate** | `(duplicate_addresses / total) × 100` | ≤ 5% |
| **Overall Quality** | Weighted avg of above | ≥ 80% |

### 11.3 Before vs After Comparison

```python
# geocare/domain/value_objects/quality_report.py (conceptual)

@dataclass
class QualityReport:
    # Pre-processing
    total_records: int
    complete_addresses_before: int
    missing_pincode_before: int
    missing_locality_before: int
    missing_city_before: int
    missing_district_before: int
    missing_state_before: int
    invalid_addresses_before: int
    duplicate_addresses_before: int
    overall_quality_before: float  # 0-100
    
    # Post-processing
    pincodes_added: int
    cities_added: int
    districts_added: int
    states_added: int
    spell_corrections: int
    improved_records: int
    manual_review_records: int
    final_quality_score: float
    improvement_percentage: float
    
    # Confidence distribution
    confidence_distribution: dict[ConfidenceTier, int]
    
    def to_comparison_dict(self) -> dict:
        return {
            "before": {
                "total_records": self.total_records,
                "complete": self.complete_addresses_before,
                "missing_pincode": self.missing_pincode_before,
                "missing_locality": self.missing_locality_before,
                "missing_city": self.missing_city_before,
                "missing_district": self.missing_district_before,
                "missing_state": self.missing_state_before,
                "invalid": self.invalid_addresses_before,
                "duplicates": self.duplicate_addresses_before,
                "quality_pct": self.overall_quality_before
            },
            "after": {
                "pincodes_added": self.pincodes_added,
                "cities_added": self.cities_added,
                "districts_added": self.districts_added,
                "states_added": self.states_added,
                "corrections": self.spell_corrections,
                "improved": self.improved_records,
                "needs_review": self.manual_review_records,
                "quality_pct": self.final_quality_score
            },
            "delta": {
                "quality_improvement": self.improvement_percentage,
                "fill_rate": (self.pincodes_added + self.cities_added + self.districts_added + self.states_added) / self.total_records
            }
        }
```

---

## 12. Confidence Engine

### 12.1 Scoring Algorithm

```mermaid
flowchart TD
    INPUT[Match Results per Component] --> WEIGHTS[Apply Weights]
    
    WEIGHTS --> W1[PIN Validity: 25%]
    WEIGHTS --> W2[Locality Match: 25%]
    WEIGHTS --> W3[Hierarchy Consistency: 20%]
    WEIGHTS --> W4[Parsing Completeness: 15%]
    WEIGHTS --> W5[Fuzzy Match Quality: 15%]
    
    W1 --> SCORE[Weighted Sum 0-100]
    W2 --> SCORE
    W3 --> SCORE
    W4 --> SCORE
    W5 --> SCORE
    
    SCORE --> TIER[Tier Classification]
    
    TIER --> HIGH[HIGH ≥ 85\nAuto-Approved]
    TIER --> MEDIUM[MEDIUM 60-84\nNeeds Review]
    TIER --> LOW[LOW 40-59\nManual Verification]
    TIER --> UNVERIFIED[UNVERIFIED < 40\nManual Verification]
```

```python
# geocare/domain/value_objects/confidence.py (conceptual)

@dataclass(frozen=True)
class ConfidenceWeights:
    pincode_validity: float = 0.25
    locality_match: float = 0.25
    hierarchy_consistency: float = 0.20
    parsing_completeness: float = 0.15
    fuzzy_quality: float = 0.15
    
    def __post_init__(self):
        total = (self.pincode_validity + self.locality_match + 
                 self.hierarchy_consistency + self.parsing_completeness + 
                 self.fuzzy_quality)
        if abs(total - 1.0) > 0.001:
            raise ValueError("Weights must sum to 1.0")


@dataclass
class ConfidenceScore:
    overall: int
    pincode_validity: int
    locality_match: int
    hierarchy_consistency: int
    parsing_completeness: int
    fuzzy_quality: int
    method: MatchMethod
    tier: ConfidenceTier
    
    @classmethod
    def calculate(
        cls,
        pincode_result: PincodeResolution | None,
        locality_result: LocalityMatch | None,
        hierarchy_result: ValidationResult,
        parsed: ParsedAddress,
        fuzzy_scores: dict[str, int],
        weights: ConfidenceWeights
    ) -> "ConfidenceScore":
        # PIN validity: 100 if exact match, 0 if missing, 50 if inferred
        pin_score = 100 if pincode_result and pincode_result.confidence == 100 else \
                    50 if pincode_result else 0
        
        # Locality match: direct from fuzzy result
        loc_score = locality_result.score if locality_result else 0
        
        # Hierarchy consistency: PostGIS validation
        hier_score = 100 if hierarchy_result.valid else max(0, 100 - len(hierarchy_result.errors) * 20)
        
        # Parsing completeness: % of components extracted
        components = [parsed.house_number, parsed.street, parsed.locality, 
                      parsed.city, parsed.district, parsed.state, parsed.pincode]
        parse_score = int((sum(1 for c in components if c) / len(components)) * 100)
        
        # Fuzzy quality: average of all fuzzy match scores
        fuzzy_score = int(sum(fuzzy_scores.values()) / len(fuzzy_scores)) if fuzzy_scores else 0
        
        # Weighted overall
        overall = int(
            weights.pincode_validity * pin_score +
            weights.locality_match * loc_score +
            weights.hierarchy_consistency * hier_score +
            weights.parsing_completeness * parse_score +
            weights.fuzzy_quality * fuzzy_score
        )
        
        # Determine tier
        if overall >= 85:
            tier = ConfidenceTier.HIGH
        elif overall >= 60:
            tier = ConfidenceTier.MEDIUM
        elif overall >= 40:
            tier = ConfidenceTier.LOW
        else:
            tier = ConfidenceTier.UNVERIFIED
        
        # Determine primary method
        method = MatchMethod.EXACT if pin_score == 100 and loc_score == 100 else \
                 MatchMethod.FUZZY if loc_score > 0 else \
                 MatchMethod.INFERRED if pin_score == 50 else \
                 MatchMethod.MANUAL
        
        return cls(
            overall=overall,
            pincode_validity=pin_score,
            locality_match=loc_score,
            hierarchy_consistency=hier_score,
            parsing_completeness=parse_score,
            fuzzy_quality=fuzzy_score,
            method=method,
            tier=tier
        )
```

### 12.2 Confidence Tier Actions

| Tier | Score Range | Action | UI Treatment |
|------|-------------|--------|--------------|
| **HIGH** | 85–100 | Auto-approve, include in default export | Green badge, no review needed |
| **MEDIUM** | 60–84 | Flag for review, include in export with warning | Yellow badge, review queue |
| **LOW** | 40–59 | Require manual verification, separate export | Orange badge, mandatory review |
| **UNVERIFIED** | 0–39 | Quarantine, separate export, manual entry | Red badge, blocked from main export |

---

## 13. Audit Engine

### 13.1 Immutable Audit Log

```mermaid
erDiagram
    AUDIT_ENTRY {
        uuid id PK
        uuid record_id FK
        string field
        string old_value
        string new_value
        string processing_method
        int confidence
        string source_dataset
        timestamp timestamp
        uuid user_id FK
    }
    
    PATIENT_RECORD ||--o{ AUDIT_ENTRY : "has"
    PROCESSING_JOB ||--o{ PATIENT_RECORD : "contains"
```

### 13.2 Audit Entry Types

| Processing Method | Description | Example |
|-------------------|-------------|---------|
| `NORMALIZATION` | Text cleanup | `"mg rd"` → `"MG Road"` |
| `PARSING` | libpostal component extraction | `"house_number": "404"` |
| `PIN_RESOLUTION` | PIN → District/State | `"500081"` → `"Hyderabad, Telangana"` |
| `LOCALITY_MATCH` | Fuzzy locality correction | `"Madapur"` → `"Madhapur"` |
| `SPELL_CORRECTION` | Spelling fix | `"Hydrabad"` → `"Hyderabad"` |
| `HIERARCHY_ENRICHMENT` | Missing component filled | `district: ""` → `"Hyderabad"` |
| `VALIDATION_CORRECTION` | PostGIS spatial fix | `city: "Secunderabad"` → `"Hyderabad"` |
| `MANUAL_OVERRIDE` | User correction | Analyst changes city |

### 13.3 Audit Trail Query API

```python
# geocare/application/use_cases/audit.py (conceptual)

class AuditUseCase:
    async def get_record_audit(self, record_id: UUID) -> list[AuditEntry]:
        """Full transformation history for a single record."""
        return await self.audit_repo.get_for_record(record_id)
    
    async def get_job_audit_summary(self, job_id: UUID) -> AuditSummary:
        """Aggregate audit stats for a job."""
        entries = await self.audit_repo.get_for_job(job_id)
        return AuditSummary(
            total_changes=len(entries),
            by_method=Counter(e.processing_method for e in entries),
            by_field=Counter(e.field for e in entries),
            avg_confidence=mean(e.confidence for e in entries),
            user_overrides=sum(1 for e in entries if e.user_id)
        )
    
    async def export_audit_trail(self, job_id: UUID, format: str) -> AsyncIterator[bytes]:
        """Stream audit trail as CSV/Parquet."""
        async for batch in self.audit_repo.stream_for_job(job_id, batch_size=10000):
            yield self._serialize_batch(batch, format)
```

---

## 14. Background Job Architecture

### 14.1 Celery Task Structure

```mermaid
flowchart TD
    ENQUEUE[API Enqueues Job] --> ROUTE[Route to Queue]
    ROUTE --> Q_HIGH[Queue: high-priority\nProfile, Small Jobs]
    ROUTE --> Q_STD[Queue: standard\nBatch Processing]
    ROUTE --> Q_LOW[Queue: low-priority\nExports, Reports]
    
    Q_HIGH --> WORKER_HIGH[Worker Pool: High\nConcurrence: 8]
    Q_STD --> WORKER_STD[Worker Pool: Standard\nConcurrence: 16]
    Q_LOW --> WORKER_LOW[Worker Pool: Low\nConcurrence: 4]
    
    WORKER_HIGH --> RESULT[Redis Result Backend]
    WORKER_STD --> RESULT
    WORKER_LOW --> RESULT
    
    RESULT --> CALLBACK[Progress Callback\n→ API → WebSocket]
    RESULT --> STORE[Persist to PostgreSQL]
```

### 14.2 Task Definitions

```python
# geocare/infrastructure/queue/tasks.py (conceptual)

from celery import Task
from geocare.infrastructure.queue.celery_app import celery_app

class BaseTask(Task):
    """Base task with error handling, retry, and progress reporting."""
    
    autoretry_for = (Exception,)
    retry_backoff = True
    retry_backoff_max = 600  # 10 minutes
    retry_jitter = True
    max_retries = 3
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        job_id = kwargs.get('job_id')
        if job_id:
            # Update job status to FAILED
            asyncio.run(self._mark_job_failed(job_id, str(exc)))
    
    def on_success(self, retval, task_id, args, kwargs):
        job_id = kwargs.get('job_id')
        chunk_index = kwargs.get('chunk_index')
        if job_id and chunk_index is not None:
            asyncio.run(self._update_progress(job_id, chunk_index))

@celery_app.task(base=BaseTask, bind=True, queue='standard')
def process_batch(self, job_id: str, chunk_index: int, chunk_path: str) -> dict:
    """Process a single batch of records."""
    # 1. Load chunk from storage (S3/local)
    df = pl.read_parquet(chunk_path)
    
    # 2. Process through pipeline
    results = asyncio.run(process_batch_pipeline(df, job_id))
    
    # 3. Persist results
    asyncio.run(persist_batch_results(job_id, chunk_index, results))
    
    # 4. Return progress info
    return {
        "job_id": job_id,
        "chunk_index": chunk_index,
        "processed": len(results),
        "succeeded": sum(1 for r in results if r.confidence.tier != ConfidenceTier.UNVERIFIED),
        "failed": sum(1 for r in results if r.confidence.tier == ConfidenceTier.UNVERIFIED)
    }

@celery_app.task(base=BaseTask, bind=True, queue='high')
def profile_dataset(self, job_id: str, file_path: str) -> dict:
    """Profile dataset and detect address columns."""
    df = pl.scan_parquet(file_path).collect()
    profile = asyncio.run(profile_dataframe(df))
    return {"job_id": job_id, "profile": profile}

@celery_app.task(base=BaseTask, bind=True, queue='low')
def export_results(self, job_id: str, format: str, filters: dict) -> str:
    """Generate export file and return S3 path."""
    export_path = asyncio.run(generate_export(job_id, format, filters))
    return export_path

@celery_app.task(base=BaseTask, bind=True, queue='low')
def generate_report(self, job_id: str) -> dict:
    """Generate before/after quality report."""
    report = asyncio.run(build_quality_report(job_id))
    return {"job_id": job_id, "report": report}
```

### 14.3 Worker Configuration

| Pool | Queue | Concurrency | Memory Limit | Use Case |
|------|-------|-------------|--------------|----------|
| **High** | `high-priority` | 8 | 2 GB | Profiling, small jobs (<10k rows) |
| **Standard** | `standard` | 16 | 4 GB | Main batch processing |
| **Low** | `low-priority` | 4 | 2 GB | Exports, reports, geography refresh |
| **Dedicated** | `geo-refresh` | 2 | 8 GB | OSM import, index rebuild |

### 14.4 Job Lifecycle Management

```mermaid
stateDiagram-v2
    [*] --> CREATED: POST /jobs
    CREATED --> QUEUED: Enqueue batches
    QUEUED --> PROCESSING: Worker starts
    PROCESSING --> PROCESSING: Batch complete (checkpoint)
    PROCESSING --> COMPLETED: All batches done
    PROCESSING --> FAILED: Max retries exceeded
    PROCESSING --> CANCELLED: User cancels
    FAILED --> QUEUED: User retries
    COMPLETED --> [*]
    CANCELLED --> [*]
    
    note right of PROCESSING
        Checkpoints saved every batch:
        - completed_chunks: [0, 1, 2...]
        - failed_chunks: [5]
        - progress: 45%
    end note
```

### 14.5 Dead Letter Handling

```python
# geocare/infrastructure/queue/dead_letter.py (conceptual)

@celery_app.task(bind=True, max_retries=0, queue='dead-letter')
def handle_failed_task(self, original_task_name: str, args: list, kwargs: dict, 
                       exception: str, traceback: str, retries: int):
    """Handle tasks that exhausted all retries."""
    # 1. Log to dead letter table
    asyncio.run(log_dead_letter(original_task_name, args, kwargs, exception, traceback, retries))
    
    # 2. Update job status if all chunks failed
    job_id = kwargs.get('job_id')
    if job_id:
        asyncio.run(check_job_all_failed(job_id))
    
    # 3. Alert admin (email/Slack)
    asyncio.run(alert_on_dlq(original_task_name, job_id, exception))
```

---

## 15. Database Architecture

### 15.1 PostgreSQL Schema (Primary DB)

```mermaid
erDiagram
    USERS ||--o{ PROCESSING_JOBS : "owns"
    PROCESSING_JOBS ||--o{ PATIENT_RECORDS : "contains"
    PROCESSING_JOBS ||--o{ JOB_CHUNKS : "split into"
    PATIENT_RECORDS ||--o{ AUDIT_ENTRIES : "has"
    
    USERS {
        uuid id PK
        string email UK
        string password_hash
        string full_name
        string role "admin/analyst/viewer"
        boolean is_active
        timestamp created_at
        timestamp last_login
    }
    
    PROCESSING_JOBS {
        uuid id PK
        uuid user_id FK
        string filename
        int total_rows
        jsonb column_mapping
        string status "pending/profiling/queued/processing/completed/failed/cancelled"
        jsonb completed_chunks
        jsonb failed_chunks
        float progress_pct
        timestamp started_at
        timestamp completed_at
        string error_message
        jsonb stats
    }
    
    JOB_CHUNKS {
        uuid id PK
        uuid job_id FK
        int chunk_index
        string storage_path "S3/local path"
        int row_count
        string status "pending/processing/completed/failed"
        int retry_count
        timestamp started_at
        timestamp completed_at
    }
    
    PATIENT_RECORDS {
        uuid id PK
        uuid job_id FK
        int row_index
        string patient_id_hash "SHA256(patient_id + salt)"
        jsonb original_address "raw input components"
        jsonb normalized_address "after normalization"
        jsonb parsed_address "libpostal output"
        jsonb enriched_address "final canonical components"
        jsonb confidence_score "breakdown + overall"
        string review_status "auto/needs_review/manual_verified"
        timestamp created_at
        timestamp updated_at
        point geometry "PostGIS point for choropleth"
    }
    
    AUDIT_ENTRIES {
        uuid id PK
        uuid record_id FK
        string field "column name"
        string old_value
        string new_value
        string processing_method "normalization/parsing/pin_resolution/..."
        int confidence
        string source_dataset "india_post/osm/census/manual"
        timestamp timestamp
        uuid user_id FK "nullable"
    }
```

### 15.2 Partitioning Strategy

```sql
-- Partition patient_records by job_id for efficient cleanup/archival
CREATE TABLE patient_records (
    id UUID DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL,
    row_index INT NOT NULL,
    patient_id_hash TEXT,
    original_address JSONB,
    normalized_address JSONB,
    parsed_address JSONB,
    enriched_address JSONB,
    confidence_score JSONB,
    review_status TEXT DEFAULT 'auto',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    geometry GEOGRAPHY(POINT, 4326)
) PARTITION BY HASH (job_id);

-- Create 16 partitions (adjust based on expected concurrent jobs)
CREATE TABLE patient_records_p0 PARTITION OF patient_records FOR VALUES WITH (MODULUS 16, REMAINDER 0);
-- ... p1 through p15

-- Indexes
CREATE INDEX idx_patient_records_job_id ON patient_records(job_id);
CREATE INDEX idx_patient_records_review_status ON patient_records(review_status) WHERE review_status != 'auto';
CREATE INDEX idx_patient_records_geometry ON patient_records USING GIST(geometry);
CREATE INDEX idx_audit_entries_record_id ON audit_entries(record_id);
CREATE INDEX idx_jobs_user_status ON processing_jobs(user_id, status);
```

### 15.3 Geography Reference Tables

```sql
-- PIN Code Directory (India Post)
CREATE TABLE pincode_directory (
    pincode CHAR(6) PRIMARY KEY,
    office_name TEXT NOT NULL,
    office_type TEXT, -- "Head Office", "Sub Office", "Branch Office"
    delivery_status TEXT, -- "Delivery", "Non-Delivery"
    district TEXT NOT NULL,
    state TEXT NOT NULL,
    taluk TEXT,
    circle TEXT,
    region TEXT,
    division TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    localities TEXT[], -- array of locality names
    source_version TEXT,
    loaded_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_pincode_district_state ON pincode_directory(district, state);

-- Locality Dictionary (India Post + OSM + Census)
CREATE TABLE locality_dictionary (
    id BIGSERIAL PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    aliases TEXT[], -- alternative spellings/names
    pincode CHAR(6) NOT NULL REFERENCES pincode_directory(pincode),
    city TEXT NOT NULL,
    district TEXT NOT NULL,
    state TEXT NOT NULL,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    population BIGINT,
    source TEXT NOT NULL, -- 'india_post', 'osm', 'census'
    source_version TEXT,
    loaded_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_locality_canonical ON locality_dictionary(canonical_name);
CREATE INDEX idx_locality_pincode ON locality_dictionary(pincode);
CREATE INDEX idx_locality_city_district ON locality_dictionary(city, district);
CREATE INDEX idx_locality_aliases ON locality_dictionary USING GIN(aliases);

-- Census Hierarchy
CREATE TABLE census_hierarchy (
    state_code CHAR(2) PRIMARY KEY,
    state_name TEXT NOT NULL,
    district_code CHAR(4),
    district_name TEXT,
    subdistrict_code CHAR(6),
    subdistrict_name TEXT,
    village_code CHAR(8),
    village_name TEXT,
    level TEXT, -- 'State', 'District', 'Sub-district', 'Village', 'Town'
    population BIGINT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION
);

CREATE INDEX idx_census_state ON census_hierarchy(state_code);
CREATE INDEX idx_census_district ON census_hierarchy(district_code);
CREATE INDEX idx_census_name ON census_hierarchy(state_name, district_name, village_name);
```

### 15.4 Redis Schema

| Key Pattern | Type | TTL | Description |
|-------------|------|-----|-------------|
| `job:{job_id}:status` | String | 24h | Current job status |
| `job:{job_id}:progress` | Hash | 24h | `processed`, `total`, `current_batch`, `pct` |
| `job:{job_id}:chunks` | List | 24h | Completed chunk indices |
| `fuzzy:{query_hash}` | String (JSON) | 24h | Cached fuzzy match results |
| `worker:{worker_id}:heartbeat` | String | 60s | Worker liveness |
| `rate_limit:{user_id}:{endpoint}` | String | 60s | API rate limiting |
| `session:{session_id}` | Hash | 7d | User session data |

### 15.5 OSM PostGIS Database (Separate Instance)

```sql
-- Dedicated schema for OSM boundaries
CREATE SCHEMA osm;

CREATE TABLE osm.admin_boundaries (
    id BIGSERIAL PRIMARY KEY,
    osm_id BIGINT NOT NULL,
    admin_level SMALLINT NOT NULL, -- 4=state, 6=district, 8=city, 10=village
    name TEXT NOT NULL,
    name_en TEXT,
    name_hi TEXT,
    tags JSONB,
    geom GEOMETRY(MULTIPOLYGON, 4326) NOT NULL,
    way_area DOUBLE PRECISION,
    loaded_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_osm_admin_level ON osm.admin_boundaries(admin_level);
CREATE INDEX idx_osm_name ON osm.admin_boundaries(name);
CREATE INDEX idx_osm_geom ON osm.admin_boundaries USING GIST(geom);

-- Materialized views for dashboard choropleth
CREATE MATERIALIZED VIEW osm.state_boundaries AS
SELECT osm_id, name, name_en, geom FROM osm.admin_boundaries WHERE admin_level = 4;

CREATE MATERIALIZED VIEW osm.district_boundaries AS
SELECT osm_id, name, name_en, geom FROM osm.admin_boundaries WHERE admin_level = 6;

-- Refresh after OSM import
CREATE OR REPLACE FUNCTION osm.refresh_choropleth_views()
RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY osm.state_boundaries;
    REFRESH MATERIALIZED VIEW CONCURRENTLY osm.district_boundaries;
END $$;
```

---

## 16. API Architecture

### 16.1 REST Endpoint Map

```mermaid
graph TD
    API[/api/v1]
    
    API --> AUTH[/auth]
    AUTH --> LOGIN[POST /login]
    AUTH --> REFRESH[POST /refresh]
    AUTH --> LOGOUT[POST /logout]
    AUTH --> ME[GET /me]
    
    API --> FILES[/files]
    FILES --> UPLOAD[POST /upload]
    FILES --> PROFILE[GET /{file_id}/profile]
    FILES --> CONFIRM[POST /{file_id}/confirm-columns]
    
    API --> JOBS[/jobs]
    JOBS --> CREATE[POST /]
    JOBS --> LIST[GET /]
    JOBS --> GET[GET /{job_id}]
    JOBS --> PROGRESS[GET /{job_id}/stream]
    JOBS --> CANCEL[POST /{job_id}/cancel]
    JOBS --> RETRY[POST /{job_id}/retry]
    JOBS --> REPORT[GET /{job_id}/report]
    JOBS --> EXPORT[GET /{job_id}/export]
    JOBS --> AUDIT[GET /{job_id}/audit]
    
    API --> DASHBOARD[/dashboard]
    DASHBOARD --> OVERVIEW[GET /overview]
    DASHBOARD --> GEOGRAPHY[GET /geography]
    DASHBOARD --> QUALITY[GET /quality]
    DASHBOARD --> JOBS_LIST[GET /jobs]
    
    API --> ADMIN[/admin]
    ADMIN --> USERS[GET/POST /users]
    ADMIN --> GEO_REFRESH[POST /geography/refresh]
    ADMIN --> GEO_STATUS[GET /geography/status]
    ADMIN --> SYSTEM[GET /system/health]
```

### 16.2 Request/Response Schemas (Key Examples)

```python
# geocare/presentation/api/schemas.py (conceptual)

class FileUploadResponse(BaseModel):
    file_id: UUID
    filename: str
    size_bytes: int
    row_count: int
    column_count: int
    columns: list[ColumnInfo]
    detected_address_columns: list[str]

class ColumnInfo(BaseModel):
    name: str
    dtype: str
    null_pct: float
    distinct_count: int
    sample_values: list[str]
    min_length: int
    max_length: int
    pattern_regex: str | None

class JobCreateRequest(BaseModel):
    file_id: UUID
    column_mapping: ColumnMapping
    chunk_size: int = 50000

class ColumnMapping(BaseModel):
    patient_id: str | None = None
    address_line_1: str | None = None
    address_line_2: str | None = None
    landmark: str | None = None
    pincode: str | None = None
    city: str | None = None
    district: str | None = None
    state: str | None = None
    country: str | None = None

class JobResponse(BaseModel):
    job_id: UUID
    status: JobStatus
    progress_pct: float
    total_rows: int
    processed_rows: int
    succeeded_rows: int
    failed_rows: int
    started_at: datetime | None
    completed_at: datetime | None
    error: str | None

class QualityReportResponse(BaseModel):
    before: QualityMetrics
    after: QualityMetrics
    delta: QualityDelta
    confidence_distribution: dict[ConfidenceTier, int]

class ExportRequest(BaseModel):
    format: Literal["csv", "xlsx", "parquet"]
    confidence_tiers: list[ConfidenceTier] | None = None
    include_audit: bool = False
    include_original: bool = True
```

### 16.3 WebSocket Progress Protocol

```typescript
// Frontend WebSocket message types

interface ProgressMessage {
  type: "progress";
  job_id: string;
  processed: number;
  total: number;
  current_batch: number;
  total_batches: number;
  pct: number;
  rate: number; // rows/sec
  eta_seconds: number;
}

interface StatusMessage {
  type: "status";
  job_id: string;
  status: "queued" | "processing" | "completed" | "failed" | "cancelled";
  error?: string;
}

interface BatchCompleteMessage {
  type: "batch_complete";
  job_id: string;
  batch_index: number;
  succeeded: number;
  failed: number;
}

// Server-Sent Events fallback
// GET /api/v1/jobs/{job_id}/stream
// Event stream: data: {"type": "progress", ...}\n\n
```

### 16.4 API Versioning & Deprecation

- **Version in URL**: `/api/v1/`
- **Deprecation Header**: `Sunset: Sat, 01 Jan 2026 00:00:00 GMT`
- **Breaking changes**: New major version (`/api/v2/`)
- **Backward compatibility**: 12 months minimum

---

## 17. Security Architecture

### 17.1 Authentication Flow

```mermaid
sequenceDiagram
    participant User
    participant FE as Frontend
    participant API as FastAPI
    participant Redis
    participant DB as PostgreSQL
    
    User->>FE: Enter credentials
    FE->>API: POST /auth/login {email, password}
    API->>DB: Verify user + bcrypt(password)
    DB-->>API: User record
    API->>API: Generate JWT pair (access + refresh)
    API->>Redis: Store refresh_token hash (TTL 7d)
    API->>Redis: Store session metadata
    API-->>FE: Set-Cookie: access_token (HttpOnly, Secure, SameSite=Strict)<br/>Set-Cookie: refresh_token (HttpOnly, Secure, SameSite=Strict)
    FE-->>User: Redirect to dashboard
    
    Note over API,Redis: Access token: 15 min, RS256<br/>Refresh token: 7 days, rotated on use
```

### 17.2 Authorization (RBAC)

| Role | Permissions |
|------|-------------|
| **Admin** | All endpoints, user management, geography refresh, system health |
| **Analyst** | Upload files, create jobs, view reports, export results, dashboard |
| **Viewer** | View jobs, view reports, view dashboard, download exports (own jobs) |

```python
# geocare/presentation/api/deps.py (conceptual)

from fastapi import Depends, HTTPException, status
from geocare.domain.entities import User, Role

async def get_current_user(
    access_token: str = Cookie(alias="access_token"),
    db: AsyncSession = Depends(get_db)
) -> User:
    payload = decode_jwt(access_token)
    user = await user_repo.get(payload.sub)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user

def require_role(*allowed: Role):
    async def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return Depends(checker)

# Usage
@router.post("/admin/geography/refresh", dependencies=[Depends(require_role(Role.ADMIN))])
async def refresh_geography(): ...
```

### 17.3 Data Protection

| Layer | Mechanism |
|-------|-----------|
| **Transport** | TLS 1.3 enforced (HSTS, secure cookies) |
| **At Rest (DB)** | PostgreSQL TDE (transparent data encryption) + column-level AES-256 for PII |
| **At Rest (Files)** | S3 SSE-KMS / LUKS encrypted volumes |
| **PII Handling** | Patient ID hashed (SHA-256 + salt) before storage; original never persisted |
| **Audit Logs** | Immutable append-only; signed with HMAC |
| **Secrets** | HashiCorp Vault / AWS Secrets Manager; injected at runtime |

### 17.4 File Upload Security

```python
# geocare/presentation/api/upload.py (conceptual)

ALLOWED_MIME_TYPES = {
    "text/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
}

MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB

async def validate_upload(file: UploadFile) -> ValidationResult:
    # 1. Check MIME type
    if file.content_type not in ALLOWED_MIME_TYPES:
        return ValidationResult(valid=False, error="Unsupported file type")
    
    # 2. Check extension
    ext = Path(file.filename).suffix.lower()
    if ext not in ('.csv', '.xlsx', '.xls'):
        return ValidationResult(valid=False, error="Invalid extension")
    
    # 3. Stream to temp + virus scan (ClamAV)
    temp_path = await save_to_temp(file)
    scan_result = await clamd_scan(temp_path)
    if scan_result.infected:
        await delete_file(temp_path)
        return ValidationResult(valid=False, error="Virus detected")
    
    # 4. Validate structure (header row, encoding)
    try:
        df = pl.read_csv(temp_path, n_rows=1) if ext == '.csv' else pl.read_excel(temp_path, n_rows=1)
    except Exception as e:
        await delete_file(temp_path)
        return ValidationResult(valid=False, error=f"Parse error: {e}")
    
    return ValidationResult(valid=True, temp_path=temp_path, columns=df.columns)
```

---

## 18. Performance Architecture

### 18.1 Latency Budgets

| Operation | Target (p95) | Target (p99) |
|-----------|--------------|--------------|
| File upload (2 GB) | 5 min | 10 min |
| Profiling (100k rows) | 10 s | 30 s |
| Single record processing | 50 ms | 100 ms |
| Batch (50k rows) | 2 min | 5 min |
| API response (job status) | 200 ms | 500 ms |
| Dashboard query (10M rows agg) | 2 s | 5 s |
| Export generation (1M rows) | 30 s | 2 min |
| Fuzzy match (cached) | 5 ms | 20 ms |
| Fuzzy match (cold) | 50 ms | 100 ms |

### 18.2 Optimization Strategies

| Layer | Technique | Impact |
|-------|-----------|--------|
| **Processing** | Polars streaming + vectorized ops | 10-50x vs Pandas |
| **Processing** | Chunked batches (50k) + parallel workers | Linear horizontal scaling |
| **Geography** | In-memory PIN dict + BK-Tree + Redis cache | O(1) PIN, <50ms fuzzy |
| **Database** | Partitioned tables + BRIN indexes + materialized views | Sub-second dashboard queries |
| **Database** | COPY for bulk inserts, asyncpg connection pool | 100k rows/sec insert |
| **Cache** | Redis fuzzy cache (24h TTL) | 80%+ cache hit rate |
| **Export** | Streaming Parquet + async S3 upload | Constant memory, parallel download |
| **Frontend** | React Query caching + virtualized tables | Smooth 10k+ row tables |

### 18.3 Resource Sizing (10M Records Baseline)

| Component | Specification | Justification |
|-----------|---------------|---------------|
| **API Pods** | 3-20 × 2 vCPU, 4 GiB | HPA on RPS > 100 |
| **Worker Pods** | 2-30 × 4 vCPU, 8 GiB | KEDA on queue depth > 50 |
| **PostgreSQL** | db.r6g.2xlarge (8 vCPU, 64 GiB) | 10M records + geo indexes |
| **OSM PostGIS** | db.r6g.xlarge (4 vCPU, 32 GiB) | Boundary polygons + spatial idx |
| **Redis** | cache.r6g.large × 3 shards | Fuzzy cache + queue + sessions |
| **S3/MinIO** | 500 GB + versioning | Uploads, exports, Parquet chunks |

---

## 19. Scalability Strategy

### 19.1 Horizontal Scaling Triggers

```mermaid
flowchart TD
    METRICS[Prometheus Metrics] --> KEDA[KEDA ScaledObject]
    KEDA --> WORKERS[Celery Workers]
    
    METRICS --> HPA_API[HPA: API Pods]
    HPA_API --> API[FastAPI Pods]
    
    METRICS --> HPA_FE[HPA: Frontend Pods]
    HPA_FE --> FE[Next.js Pods]
    
    WORKERS -.->|queue: standard| Q_STD
    WORKERS -.->|queue: high| Q_HIGH
    WORKERS -.->|queue: low| Q_LOW
    
    Q_STD -->|depth > 50| SCALE_UP[Add Workers]
    Q_STD -->|depth < 10| SCALE_DOWN[Remove Workers]
    HPA_API -->|RPS > 100| SCALE_API
    HPA_API -->|RPS < 20| SHRINK_API
```

### 19.2 Scaling Dimensions

| Dimension | Mechanism | Max Scale |
|-----------|-----------|-----------|
| **API Throughput** | HPA (CPU/RPS) | 50 pods |
| **Batch Throughput** | KEDA (queue depth) | 100 workers |
| **Geography Lookups** | In-memory (replicated per worker) | N workers |
| **Database Reads** | Read replicas | 5 replicas |
| **Cache** | Redis Cluster (shards) | 6 shards |
| **File Storage** | S3/MinIO (unlimited) | PB scale |

### 19.3 10M Record Processing Estimate

| Phase | Time (16 workers, 4 vCPU each) |
|-------|--------------------------------|
| Upload & Profile | 5 min |
| Chunking (50k/batch = 200 chunks) | 2 min |
| Parallel Processing (200 batches / 16 workers) | 18 min |
| Report Generation | 3 min |
| Export Preparation | 5 min |
| **Total** | **~33 minutes** |

---

## 20. Fault Tolerance

### 20.1 Failure Modes & Mitigations

| Failure | Detection | Mitigation | Recovery |
|---------|-----------|------------|----------|
| **Worker crash mid-batch** | Heartbeat missing (60s) | Task requeued (Celery ack_late) | Resume from last checkpoint |
| **DB connection loss** | SQLAlchemy pool timeout | Retry with exponential backoff | Auto-reconnect, resume |
| **Redis unavailable** | Connection error | Fallback to in-memory queue (local) | Reconnect, flush local queue |
| **OOM in worker** | Container OOMKilled | Memory limit + chunk size tuning | K8s restarts pod, task requeued |
| **Disk full (uploads)** | Prometheus alert > 80% | Auto-cleanup old exports (TTL 30d) | Alert admin, manual cleanup |
| **Geography index corruption** | Startup validation fails | Rebuild from PostgreSQL source | Auto-rebuild on startup |
| **OSM import failure** | osm2pgsql exit code ≠ 0 | Retry with clean DB, alert | Manual intervention |

### 20.2 Retry Policies

```python
# geocare/infrastructure/queue/celery_app.py (conceptual)

celery_app.conf.task_acks_late = True
celery_app.conf.task_reject_on_worker_lost = True
celery_app.conf.task_default_retry_delay = 60  # 1 min
celery_app.conf.task_max_retries = 3
celery_app.conf.task_retry_backoff = True
celery_app.conf.task_retry_backoff_max = 600  # 10 min
celery_app.conf.task_retry_jitter = True
```

### 20.3 Data Durability Guarantees

| Data | Durability Mechanism |
|------|---------------------|
| **Uploaded files** | S3 versioning + cross-region replication |
| **Job metadata** | PostgreSQL WAL + daily pg_dump to S3 |
| **Patient records** | PostgreSQL WAL + partitioned tables |
| **Audit entries** | Append-only table + monthly partition rotation |
| **Geography data** | Source CSVs versioned in S3 + DB snapshots |
| **Redis cache** | RDB snapshots + AOF; non-critical (rebuildable) |

---

## 21. Sequence Diagrams

### 21.1 File Upload to Job Creation

```mermaid
sequenceDiagram
    actor User
    participant FE as Frontend
    participant API as FastAPI
    participant Redis
    participant DB as PostgreSQL
    participant S3 as Object Storage
    participant Worker as Celery Worker
    
    User->>FE: Select CSV/Excel file
    FE->>API: POST /files/upload (multipart)
    API->>S3: Stream upload to temp bucket
    API->>Redis: Set file:{id}:status=uploaded
    API-->>FE: {file_id, columns[], preview[]}
    
    FE->>API: GET /files/{file_id}/profile
    API->>S3: Download sample (10k rows)
    API->>API: Polars profile + column detection
    API-->>FE: ProfileReport {stats, detected_address_cols}
    
    User->>FE: Confirm/adjust column mapping
    FE->>API: POST /files/{file_id}/confirm-columns
    API->>DB: CREATE job (status=PROFILING)
    API->>S3: Convert full file to Parquet chunks
    API->>DB: CREATE job_chunks (status=PENDING)
    API->>Redis: LPUSH queue:standard job_chunks[]
    API-->>FE: {job_id}
    
    FE->>API: GET /jobs/{job_id}/stream (SSE)
    API->>Redis: SUBSCRIBE job:{job_id}:progress
```

### 21.2 Batch Processing Loop

```mermaid
sequenceDiagram
    participant Worker as Celery Worker
    participant Redis
    participant DB as PostgreSQL
    participant Geo as Geography Engine
    participant S3
    
    loop For each chunk
        Worker->>Redis: BRPOP queue:standard (timeout=30s)
        Redis-->>Worker: chunk_id, chunk_path
        Worker->>DB: UPDATE job_chunks SET status=PROCESSING
        Worker->>S3: Download chunk Parquet
        Worker->>Geo: process_batch(chunk_df)
        
        par Parallel Stages
            Geo->>Geo: Normalize addresses
            Geo->>Geo: Parse with libpostal
            Geo->>Geo: Fuzzy match localities
            Geo->>Geo: Resolve PIN codes
            Geo->>Geo: Enrich hierarchy
            Geo->>Geo: Validate with PostGIS
            Geo->>Geo: Calculate confidence
            Geo->>Geo: Create audit entries
        end
        
        Worker->>DB: Bulk INSERT patient_records + audit_entries
        Worker->>DB: UPDATE job_chunks SET status=COMPLETED
        Worker->>Redis: HINCRBY job:{id}:processed N
        Worker->>Redis: PUBLISH job:{id}:progress {pct, rate, eta}
    end
    
    Worker->>DB: UPDATE jobs SET status=COMPLETED
    Worker->>Redis: PUBLISH job:{id}:status COMPLETED
```

### 21.3 Geography Data Refresh

```mermaid
sequenceDiagram
    participant Admin
    participant API
    participant Worker as Geo Refresh Worker
    participant S3
    participant DB as PostgreSQL
    participant OSM_DB as OSM PostGIS
    participant Redis
    
    Admin->>API: POST /admin/geography/refresh
    API->>DB: CREATE refresh_job (status=DOWNLOADING)
    API->>Worker: ENQUEUE geo_refresh_task
    
    Worker->>S3: Download India Post PIN CSV (latest)
    Worker->>S3: Download Census hierarchy CSV
    Worker->>S3: Download OSM India PBF (Geofabrik)
    Worker->>Worker: Verify checksums
    
    Worker->>DB: TRUNCATE pincode_directory; COPY FROM CSV
    Worker->>DB: TRUNCATE census_hierarchy; COPY FROM CSV
    Worker->>OSM_DB: osm2pgsql --slim --flat-nodes PBF → admin_boundaries
    Worker->>OSM_DB: REFRESH MATERIALIZED VIEWS
    
    Worker->>Worker: Build in-memory PIN index, BK-Tree, Trie
    Worker->>Redis: Warm fuzzy cache (top 100k localities)
    
    Worker->>DB: UPDATE refresh_job SET status=COMPLETED, version=new
    Worker->>Redis: PUBLISH geography:refreshed {version}
    API->>Admin: Notify success
```

---

## 22. Data Flow Diagrams

### 22.1 Main Processing Data Flow (DFD Level 1)

```mermaid
flowchart LR
    USER[Hospital User] -->|1. Upload CSV/Excel| FE[Frontend]
    FE -->|2. Stream to API| API[FastAPI]
    API -->|3. Store chunks| S3[(Object Storage)]
    API -->|4. Create Job| DB[(PostgreSQL)]
    API -->|5. Enqueue Batches| Redis[(Redis Queue)]
    
    subgraph Workers[Worker Pool]
        W1[Worker 1]
        W2[Worker 2]
        WN[Worker N]
    end
    
    Redis -->|6. Dequeue Batch| Workers
    Workers -->|7. Load Chunk| S3
    Workers -->|8. Process Pipeline| GEO[Geography Engine]
    GEO -->|9. Reference Data| DB
    GEO -->|10. Spatial Validation| OSM_DB[(OSM PostGIS)]
    GEO -->|11. Fuzzy Cache| Redis
    Workers -->|12. Persist Results| DB
    Workers -->|13. Update Progress| Redis
    Redis -->|14. SSE Progress| API
    API -->|15. Stream Updates| FE
    FE -->|16. Show Progress| USER
    
    USER -->|17. Request Export| FE
    FE -->|18. Export API| API
    API -->|19. Stream Query| DB
    API -->|20. Generate File| S3
    API -->|21. Presigned URL| FE
    FE -->|22. Download| USER
```

### 22.2 Geography Engine Internal Flow

```mermaid
flowchart TD
    INPUT[ParsedAddress Components] --> PIN{PIN Present?}
    PIN -- Yes --> PIN_LOOKUP[PIN Index: O(1) Exact]
    PIN -- No --> PIN_INFER[Infer from Locality/City]
    
    PIN_LOOKUP --> PIN_RESULT[PincodeResolution\nDistrict, State, Taluk, Lat/Lon]
    PIN_INFER --> REV_LOOKUP[Reverse PIN Index\nLocality → PIN Candidates]
    REV_LOOKUP --> PIN_RESULT
    
    PIN_RESULT --> CONTEXT[Build GeoContext\nPIN, District, State]
    
    INPUT --> LOCALITY{Locality Present?}
    LOCALITY -- Yes --> FUZZY_MATCH[Locality Fuzzy Index\nBK-Tree + Trie + RapidFuzz]
    LOCALITY -- No --> SKIP_LOCALITY
    
    FUZZY_MATCH --> CONTEXT_MATCH[Context-Aware Ranking\nPIN boost + District boost + State boost]
    CONTEXT_MATCH --> LOCALITY_RESULT[LocalityMatch\nCanonical, PIN, City, District, State, Score]
    
    LOCALITY_RESULT --> CONTEXT
    SKIP_LOCALITY --> CONTEXT
    
    CONTEXT --> HIERARCHY[Census Hierarchy\nEnrich City/District/State]
    HIERARCHY --> POSTGIS[PostGIS Validation\nPoint-in-Polygon Hierarchy]
    POSTGIS --> VALIDATION[ValidationResult\nErrors if hierarchy mismatch]
    
    VALIDATION --> SCORING[Confidence Engine\nWeighted Scoring]
    SCORING --> OUTPUT[EnrichedAddress + ConfidenceScore]
```

---

## 23. Technology Decisions (ADRs)

### ADR-001: Polars over Pandas for Data Processing

**Status**: Accepted  
**Date**: 2025-07-17

**Context**: Need to process 10M+ records with complex transformations.

**Decision**: Use Polars as primary DataFrame library.

**Consequences**:
- ✅ 10-50x faster than Pandas for large datasets
- ✅ Streaming/out-of-core processing support
- ✅ Native parallel execution (no GIL contention)
- ✅ Apache Arrow interoperability
- ❌ Smaller ecosystem than Pandas
- ❌ Learning curve for team

### ADR-002: Celery over RQ for Task Queue

**Status**: Accepted  
**Date**: 2025-07-17

**Context**: Need distributed batch processing with retries, scheduling, monitoring.

**Decision**: Celery with Redis broker.

**Consequences**:
- ✅ Mature, battle-tested at scale
- ✅ Built-in retry, rate limiting, routing
- ✅ Flower monitoring, canvas workflows
- ✅ KEDA integration for K8s autoscaling
- ❌ More complex than RQ
- ❌ Requires Redis (already needed for cache)

### ADR-003: libpostal for Address Parsing

**Status**: Accepted  
**Date**: 2025-07-17

**Context**: Need robust international address parsing, extensible for India.

**Decision**: Use libpostal via `postal` Python bindings.

**Consequences**:
- ✅ Best-in-class open-source parser
- ✅ Trained on global addresses including India
- ✅ C library = fast, embeddable
- ❌ C dependency (build complexity)
- ❌ May need custom training data for Indian formats

### ADR-004: PostgreSQL + PostGIS over ClickHouse

**Status**: Accepted  
**Date**: 2025-07-17

**Context**: Need transactional job/record storage + spatial queries for choropleth.

**Decision**: Single PostgreSQL with PostGIS extension.

**Consequences**:
- ✅ ACID for job/record integrity
- ✅ Native spatial indexes (GiST)
- ✅ Materialized views for dashboard aggregates
- ✅ Single operational database
- ❌ Analytical queries slower than ClickHouse
- ❌ Horizontal scaling harder

**Mitigation**: Partition by `job_id`, use read replicas, materialized views.

### ADR-005: Next.js App Router over Pages Router

**Status**: Accepted  
**Date**: 2025-07-17

**Context**: Modern React framework for dashboard.

**Decision**: Next.js 14+ with App Router (RSC).

**Consequences**:
- ✅ Server Components reduce client bundle
- ✅ Streaming SSR for large dashboards
- ✅ Built-in route handlers for API proxy
- ❌ Learning curve (RSC mental model)
- ❌ Some libraries not yet compatible

### ADR-006: shadcn/ui over Material UI

**Status**: Accepted  
**Date**: 2025-07-17

**Context**: Component library for dashboard.

**Decision**: shadcn/ui (Radix + Tailwind).

**Consequences**:
- ✅ Copy-paste ownership, no version lock-in
- ✅ Accessible by default (Radix primitives)
- ✅ Tailwind integration native
- ✅ Smaller bundle size
- ❌ No pre-built complex components (DataGrid, etc.)

### ADR-007: Apache ECharts over Recharts

**Status**: Accepted  
**Date**: 2025-07-17

**Context**: Charting library for analytics dashboard.

**Decision**: Apache ECharts (via `echarts-for-react`).

**Consequences**:
- ✅ Rich chart types (heatmap, sankey, choropleth)
- ✅ Excellent performance (Canvas/WebGL)
- ✅ TypeScript support
- ✅ Tree-shaking
- ❌ Imperative API (less React-idiomatic)
- ❌ Larger bundle than Recharts

---

## 24. Folder Structure

```
geocare-ai/
├── .github/
│   └── workflows/
│       ├── ci.yml              # Lint, type-check, test
│       ├── cd.yml              # Build, push, deploy
│       └── geo-refresh.yml     # Quarterly geography refresh
├── docs/
│   ├── ADR/                    # Architecture Decision Records
│   │   ├── 001-polars-over-pandas.md
│   │   ├── 002-celery-over-rq.md
│   │   ├── 003-libpostal-parser.md
│   │   ├── 004-postgresql-postgis.md
│   │   ├── 005-nextjs-app-router.md
│   │   ├── 006-shadcn-ui.md
│   │   └── 007-echarts.md
│   ├── ARCHITECTURE.md         # This document
│   ├── SRS.md                  # Software Requirements Spec
│   ├── DATABASE.md             # Schema documentation
│   ├── API.md                  # OpenAPI spec + examples
│   └── DEPLOYMENT.md           # Deploy/run instructions
├── docker/
│   ├── docker-compose.yml      # Development stack
│   ├── docker-compose.prod.yml # Production overrides
│   ├── Dockerfile.backend      # Multi-stage build
│   ├── Dockerfile.frontend     # Multi-stage build
│   ├── Dockerfile.worker       # Worker-specific
│   └── nginx.conf              # Reverse proxy config
├── backend/
│   ├── src/
│   │   └── geocare/
│   │       ├── __init__.py
│   │       ├── config/
│   │       │   ├── __init__.py
│   │       │   ├── settings.py          # Pydantic Settings
│   │       │   ├── logging.py           # Structured logging
│   │       │   └── container.py         # DI container (dependency-injector)
│   │       ├── domain/
│   │       │   ├── __init__.py
│   │       │   ├── entities/
│   │       │   │   ├── __init__.py
│   │       │   │   ├── job.py
│   │       │   │   ├── record.py
│   │       │   │   ├── geography.py
│   │       │   │   └── user.py
│   │       │   ├── value_objects/
│   │       │   │   ├── __init__.py
│   │       │   │   ├── address.py
│   │       │   │   ├── confidence.py
│   │       │   │   ├── quality.py
│   │       │   │   └── audit.py
│   │       │   ├── events/
│   │       │   │   ├── __init__.py
│   │       │   │   └── job_events.py
│   │       │   ├── ports/
│   │       │   │   ├── __init__.py
│   │       │   │   ├── repositories.py
│   │       │   │   ├── geography.py
│   │       │   │   └── queue.py
│   │       │   └── services/
│   │       │       ├── __init__.py
│   │       │       └── confidence_calculator.py
│   │       ├── application/
│   │       │   ├── __init__.py
│   │       │   ├── dto/
│   │       │   │   ├── __init__.py
│   │       │   │   ├── job.py
│   │       │   │   ├── record.py
│   │       │   │   ├── file.py
│   │       │   │   └── dashboard.py
│   │       │   ├── use_cases/
│   │       │   │   ├── __init__.py
│   │       │   │   ├── upload.py
│   │       │   │   ├── processing.py
│   │       │   │   ├── reporting.py
│   │       │   │   ├── export.py
│   │       │   │   ├── audit.py
│   │       │   │   └── geography_refresh.py
│   │       │   └── commands/
│   │       │       ├── __init__.py
│   │       │       └── processing_commands.py
│   │       ├── infrastructure/
│   │       │   ├── __init__.py
│   │       │   ├── persistence/
│   │       │   │   ├── __init__.py
│   │       │   │   ├── database.py          # SQLAlchemy engine/session
│   │       │   │   ├── models/              # ORM models
│   │       │   │   │   ├── __init__.py
│   │       │   │   │   ├── job.py
│   │       │   │   │   ├── record.py
│   │       │   │   │   ├── audit.py
│   │       │   │   │   ├── geography.py
│   │       │   │   │   └── user.py
│   │       │   │   ├── repositories/
│   │       │   │   │   ├── __init__.py
│   │       │   │   │   ├── job_repo.py
│   │       │   │   │   ├── record_repo.py
│   │       │   │   │   ├── audit_repo.py
│   │       │   │   │   └── user_repo.py
│   │       │   │   └── migrations/        # Alembic
│   │       │   ├── geography/
│   │       │   │   ├── __init__.py
│   │       │   │   ├── engine.py            # Main orchestrator
│   │       │   │   ├── pincode_index.py
│   │       │   │   ├── locality_fuzzy.py
│   │       │   │   ├── census_hierarchy.py
│   │       │   │   ├── parser_adapter.py
│   │       │   │   ├── postgis_repo.py
│   │       │   │   └── resolution.py
│   │       │   ├── queue/
│   │       │   │   ├── __init__.py
│   │       │   │   ├── celery_app.py
│   │       │   │   ├── tasks.py
│   │       │   │   ├── dead_letter.py
│   │       │   │   └── progress.py
│   │       │   ├── storage/
│   │       │   │   ├── __init__.py
│   │       │   │   ├── s3_client.py
│   │       │   │   └── local_client.py
│   │       │   └── security/
│   │       │       ├── __init__.py
│   │       │       ├── auth.py
│   │       │       ├── jwt.py
│   │       │       └── encryption.py
│   │       ├── presentation/
│   │       │   ├── __init__.py
│   │       │   ├── api/
│   │       │   │   ├── __init__.py
│   │       │   │   ├── routes/
│   │       │   │   │   ├── __init__.py
│   │       │   │   │   ├── auth.py
│   │       │   │   │   ├── files.py
│   │       │   │   │   ├── jobs.py
│   │       │   │   │   ├── reports.py
│   │       │   │   │   ├── exports.py
│   │       │   │   │   ├── dashboard.py
│   │       │   │   │   └── admin.py
│   │       │   │   ├── schemas/
│   │       │   │   │   ├── __init__.py
│   │       │   │   │   ├── requests.py
│   │       │   │   │   ├── responses.py
│   │       │   │   │   └── common.py
│   │       │   │   ├── deps.py
│   │       │   │   └── exceptions.py
│   │       │   └── ws/
│   │       │       ├── __init__.py
│   │       │       ├── progress.py
│   │       │       └── manager.py
│   │       └── main.py
│   ├── tests/
│   │   ├── unit/
│   │   │   ├── domain/
│   │   │   ├── application/
│   │   │   └── infrastructure/
│   │   ├── integration/
│   │   │   ├── api/
│   │   │   ├── geography/
│   │   │   └── processing/
│   │   ├── fixtures/
│   │   └── conftest.py
│   ├── scripts/
│   │   ├── download_geography.py
│   │   ├── build_indexes.py
│   │   ├── evaluate_accuracy.py
│   │   └── load_test_data.py
│   ├── pyproject.toml
│   ├── poetry.lock
│   ├── alembic.ini
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── (auth)/
│   │   │   │   ├── login/page.tsx
│   │   │   │   └── layout.tsx
│   │   │   ├── (dashboard)/
│   │   │   │   ├── layout.tsx
│   │   │   │   ├── page.tsx              # Overview
│   │   │   │   ├── jobs/
│   │   │   │   │   ├── page.tsx
│   │   │   │   │   └── [id]/page.tsx
│   │   │   │   ├── upload/page.tsx
│   │   │   │   ├── reports/
│   │   │   │   │   └── [id]/page.tsx
│   │   │   │   └── dashboard/
│   │   │   │       ├── geography/page.tsx
│   │   │   │       └── quality/page.tsx
│   │   │   ├── (admin)/
│   │   │   │   ├── layout.tsx
│   │   │   │   ├── users/page.tsx
│   │   │   │   └── geography/page.tsx
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx
│   │   │   ├── providers.tsx
│   │   │   └── globals.css
│   │   ├── components/
│   │   │   ├── ui/                       # shadcn/ui components
│   │   │   ├── charts/                   # ECharts wrappers
│   │   │   ├── forms/
│   │   │   ├── tables/
│   │   │   ├── layout/
│   │   │   └── job-progress.tsx
│   │   ├── hooks/
│   │   │   ├── use-job-progress.ts
│   │   │   ├── use-auth.ts
│   │   │   └── use-debounce.ts
│   │   ├── lib/
│   │   │   ├── api.ts
│   │   │   ├── auth.ts
│   │   │   ├── utils.ts
│   │   │   └── validations.ts
│   │   ├── types/
│   │   │   ├── api.ts
│   │   │   ├── job.ts
│   │   │   └── dashboard.ts
│   │   └── styles/
│   ├── tests/
│   │   ├── e2e/
│   │   │   ├── upload.spec.ts
│   │   │   ├── job-processing.spec.ts
│   │   │   └── dashboard.spec.ts
│   │   └── unit/
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── next.config.js
│   └── .env.example
├── geography-data/                    # Gitignored, mounted at runtime
│   ├── india-post/
│   ├── census/
│   └── osm/
├── scripts/
│   ├── setup-dev.sh
│   ├── run-tests.sh
│   └── benchmark.sh
├── Makefile
├── README.md
├── .gitignore
├── .dockerignore
├── .pre-commit-config.yaml
└── LICENSE
```

---

## 25. Design Patterns Used

| Pattern | Layer | Application |
|---------|-------|-------------|
| **Repository** | Infrastructure | Abstract DB access behind interfaces (`JobRepository`, `RecordRepository`) |
| **Adapter** | Infrastructure | Wrap libpostal, RapidFuzz, PostGIS behind `GeographyEngine` port |
| **Use Case / Interactor** | Application | Single-responsibility orchestration (`ProcessBatchUseCase`, `ExportUseCase`) |
| **DTO / Command / Query** | Application | Data transfer between layers (`JobCreateCommand`, `RecordExportQuery`) |
| **Entity / Value Object** | Domain | Rich domain models with invariants (`ProcessingJob`, `ConfidenceScore`) |
| **Domain Event** | Domain | Decouple side effects (`JobCompletedEvent`, `RecordEnrichedEvent`) |
| **Factory** | Domain/Application | Create complex aggregates (`RecordFactory.from_raw()`) |
| **Strategy** | Domain/Infrastructure | Pluggable scoring (`ConfidenceStrategy`), matching (`FuzzyStrategy`) |
| **Observer** | Infrastructure | Progress events via Redis pub/sub → WebSocket |
| **Circuit Breaker** | Infrastructure | Protect external calls (ClamAV, OSM download) |
| **Bulkhead** | Infrastructure | Separate worker pools per queue priority |
| **Checkpointing** | Application | Resumeable batch processing via `completed_chunks` |
| **CQRS (light)** | Application | Separate read models for dashboard (`DashboardRepository`) |

---

## 26. Future Roadmap

### Phase 1 (Post-MVP, 3 months)
- [ ] **Multi-language UI** (Hindi, regional languages)
- [ ] **Address autocomplete** in upload mapping step
- [ ] **Custom dictionary upload** (hospital-specific locality names)
- [ ] **API webhook notifications** (job complete, failure)

### Phase 2 (6 months)
- [ ] **Incremental processing** (append to existing job)
- [ ] **ML-based confidence calibration** (train on manual corrections)
- [ ] **Advanced deduplication** (cross-job, fuzzy patient matching)
- [ ] **Role-based data access** (department-level isolation)

### Phase 3 (12 months)
- [ ] **Real-time streaming mode** (Kafka + Flink for live HL7/FHIR feeds)
- [ ] **Geocoding API** (expose enrichment as internal service)
- [ ] **Multi-country support** (extend libpostal + geography packs)
- [ ] **Federated learning** (improve models across hospitals without sharing PII)

### Technical Debt & Improvements
- [ ] Migrate geography indexes to **Redisearch** (native fuzzy)
- [ ] Replace BK-Tree with **HNSW** (approximate nearest neighbor)
- [ ] **Columnar storage** (Apache Iceberg) for analytical queries
- [ ] **Vectorized UDFs** in PostgreSQL for scoring
- [ ] **WASM build** of libpostal for edge deployment

---

## 27. Appendix

### 27.1 Glossary

| Term | Definition |
|------|------------|
| **PIN** | Postal Index Number (6-digit Indian postal code) |
| **Locality** | Neighborhood/area within a city (e.g., "Madhapur", "Koramangala") |
| **Taluk/Tehsil** | Sub-district administrative unit |
| **BK-Tree** | Burkhard-Keller tree for metric space search (Levenshtein) |
| **Trie** | Prefix tree for autocomplete/prefix matching |
| **HNSW** | Hierarchical Navigable Small World (ANN index) |
| **SSE** | Server-Sent Events (unidirectional server→client) |
| **KEDA** | Kubernetes Event-driven Autoscaling |
| **osm2pgsql** | Tool to import OSM PBF into PostGIS |

### 27.2 Key Configuration Constants

```python
# geocare/config/constants.py

# Processing
DEFAULT_CHUNK_SIZE = 50_000
MAX_CHUNK_SIZE = 200_000
MIN_CHUNK_SIZE = 5_000

# Confidence
DEFAULT_CONFIDENCE_WEIGHTS = ConfidenceWeights(
    pincode_validity=0.25,
    locality_match=0.25,
    hierarchy_consistency=0.20,
    parsing_completeness=0.15,
    fuzzy_quality=0.15
)

CONFIDENCE_TIERS = {
    ConfidenceTier.HIGH: (85, 100),
    ConfidenceTier.MEDIUM: (60, 84),
    ConfidenceTier.LOW: (40, 59),
    ConfidenceTier.UNVERIFIED: (0, 39)
}

# Fuzzy Matching
FUZZY_THRESHOLD = 85
FUZZY_LIMIT = 50
BK_TREE_MAX_DIST = 2
CACHE_TTL_SECONDS = 86_400  # 24 hours

# Geography
INDIA_PIN_REGEX = r'^[1-8]\d{5}$'
PIN_CODE_COUNT = 19_100  # Approximate
LOCALITY_COUNT = 1_500_000  # Approximate

# File Limits
MAX_FILE_SIZE_MB = 2_048
MAX_FILES_PER_JOB = 50
MAX_TOTAL_ROWS = 10_000_000

# Retry
MAX_RETRIES = 3
RETRY_BASE_DELAY = 60  # seconds
RETRY_MAX_DELAY = 600  # seconds
```

---

**End of Architecture Document v1.0**