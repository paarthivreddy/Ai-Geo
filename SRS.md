# Software Requirements Specification (SRS)

## GeoCare AI – India Patient Address Intelligence Platform

---

**Version:** 1.0  
**Status:** Draft  
**Date:** 2025-07-17  
**Classification:** Internal – Enterprise Use Only

---

## 1. Introduction

### 1.1 Purpose

This document specifies the functional and non-functional requirements for **GeoCare AI**, an enterprise-grade, offline-first, AI-powered platform for enriching, validating, standardizing, and scoring Indian patient addresses from healthcare datasets.

### 1.2 Scope

GeoCare AI enables hospitals and healthcare organizations to:

- Upload patient datasets (CSV, Excel) with messy, incomplete, or misspelled addresses
- Automatically detect address columns and profile data quality
- Parse, normalize, and enrich addresses using offline Indian geographic datasets
- Resolve PIN codes, localities, cities, districts, states to canonical forms
- Score each address with a confidence metric (0–100)
- Generate before/after quality reports and audit trails
- Export enriched datasets for downstream analytics and reporting
- Process datasets up to **10 million records** in batch mode

**Geographic Scope:** India only (PIN codes, States, Districts, Cities, Taluks, Villages, Localities)  
**Operational Model:** Offline-first after initial dataset download. No paid APIs, no Google Maps, no rate limits.

### 1.3 Definitions & Acronyms

| Term | Definition |
|------|------------|
| **PIN** | Postal Index Number (6-digit Indian postal code) |
| **Locality** | Neighborhood / area / colony / sector within a city |
| **District** | Administrative unit below State |
| **Taluk / Tehsil** | Sub-district administrative unit |
| **Village / Town** | Smallest revenue/admin unit |
| **PIN → Locality Map** | Official India Post mapping of PIN → list of localities |
| **OSM** | OpenStreetMap (offline PBF extract for India) |
| **libpostal** | Open-source address parser/normalizer (C library + Python bindings) |
| **RapidFuzz** | Fast string matching / fuzzy matching library |
| **Polars** | Fast DataFrame library (Rust backend, Python API) |
| **Celery** | Distributed task queue (Redis broker) |
| **SRS** | Software Requirements Specification |

### 1.4 References

- India Post PIN Code Directory (official)
- Census of India 2011 / 2021 (village/town directory)
- OpenStreetMap India extract (Geofabrik)
- libpostal documentation
- RapidFuzz documentation
- Polars documentation
- FastAPI documentation
- PostgreSQL / PostGIS documentation

---

## 2. Functional Requirements

### 2.1 Data Ingestion

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01 | Upload CSV (UTF-8, custom delimiter) and Excel (.xlsx, .xls) files up to 2 GB per file | P0 |
| FR-02 | Support multi-file upload in a single batch job (max 50 files, 10M total rows) | P0 |
| FR-03 | Auto-detect address-related columns using header heuristics + content sampling | P0 |
| FR-04 | Present detected columns for user confirmation / correction before processing | P0 |
| FR-05 | Support column mapping: patient_id, address_line_1, address_line_2, landmark, pincode, city, district, state, country | P0 |
| FR-06 | Validate file encoding, delimiter, row count, column count before processing | P0 |
| FR-07 | Reject files with > 500 columns or > 50M rows per file with clear error | P1 |

### 2.2 Data Profiling (Pre-Processing)

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-08 | Compute per-column: null %, distinct count, sample values, min/max length, pattern regex | P0 |
| FR-09 | Detect address-like columns via keyword matching + value pattern analysis | P0 |
| FR-10 | Generate data quality baseline report: completeness, consistency, validity scores per column | P0 |
| FR-11 | Display interactive profiling dashboard before user confirms processing | P1 |

### 2.3 Address Normalization

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-12 | Unicode normalization (NFC), trim whitespace, collapse multiple spaces | P0 |
| FR-13 | Expand common abbreviations: "Rd"→"Road", "St"→"Street", "Ngr"→"Nagar", "Clny"→"Colony", "Extn"→"Extension", "Sec"→"Sector", "Blk"→"Block", "Ph"→"Phase" | P0 |
| FR-14 | Standardize case: Title Case for proper nouns, preserve acronyms (PIN, GPS) | P0 |
| FR-15 | Remove noise tokens: "Near", "Opp", "Behind", "Beside", "Near to", "Opposite" | P1 |
| FR-16 | Preserve unit/house/flat/door numbers; do not strip numerals | P0 |

### 2.4 Indian Address Parsing

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-17 | Integrate **libpostal** (via `postal` Python binding) for global address parsing | P0 |
| FR-18 | Extend libpostal with India-specific labels: `pincode`, `locality`, `sublocality`, `village`, `taluk`, `district`, `state` | P0 |
| FR-19 | Parse concatenated address lines into structured components | P0 |
| FR-20 | Handle Indian address formats: "House No, Street, Locality, City, District, State, PIN" and variants | P0 |
| FR-21 | Extract 6-digit PIN codes from any position in address text (regex + validation) | P0 |
| FR-22 | Handle bilingual addresses (English + Hindi/Devanagari script) | P1 |

### 2.5 Spelling Correction & Fuzzy Matching

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-23 | Build locality dictionary from India Post + OSM + Census (≈ 1.5M unique locality names) | P0 |
| FR-24 | Build city/district/state dictionaries from Census + India Post | P0 |
| FR-25 | Apply RapidFuzz (Levenshtein, Jaro-Winkler, token-set ratio) for fuzzy matching | P0 |
| FR-26 | Configurable similarity threshold (default 85%) per entity type | P0 |
| FR-27 | Candidate ranking: exact match > prefix match > fuzzy match > phonetic match | P0 |
| FR-28 | Handle transliteration variants: "Bengaluru" vs "Bangalore", "Mumbai" vs "Bombay" | P1 |
| FR-29 | Cache fuzzy match results in Redis for repeat lookups within job | P1 |

### 2.6 PIN Code Resolution

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-30 | Load official India Post PIN directory (≈ 19,000 PIN codes) with: pincode, office_name, office_type, delivery_status, district, state, taluk, circle, region, division | P0 |
| FR-31 | Validate PIN format: 6 digits, first digit 1–8 (India range) | P0 |
| FR-32 | PIN → (District, State) canonical mapping | P0 |
| FR-33 | PIN → List of localities (post offices) mapping | P0 |
| FR-34 | Reverse: Locality → Candidate PINs (ranked by frequency) | P0 |
| FR-35 | Detect and flag invalid/obsolete PIN codes (cross-reference with latest India Post data) | P1 |

### 2.7 Locality Resolution

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-36 | Fuzzy match input locality against dictionary (India Post office names + OSM place=* tags) | P0 |
| FR-37 | Disambiguate using context: PIN, city, district, state | P0 |
| FR-38 | Return canonical locality name + confidence score | P0 |
| FR-39 | Handle aliases: "Koramangala 4th Block" ↔ "Koramangala IV Block" | P1 |

### 2.8 City / District / State / Country Enrichment

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-40 | Enrich missing city from PIN → District → City hierarchy | P0 |
| FR-41 | Enrich missing district from PIN or State + City | P0 |
| FR-42 | Enrich missing state from PIN (direct mapping) | P0 |
| FR-43 | Country always "India" (ISO: IN) | P0 |
| FR-44 | Use Census 2011/2021 hierarchy: State → District → Sub-district → Village/Town | P0 |
| FR-45 | Map OSM admin_level (4=state, 6=district, 8=city/town, 10=village) to Census hierarchy | P1 |

### 2.9 Confidence Scoring

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-46 | Composite confidence score (0–100) per address record | P0 |
| FR-47 | Component weights (configurable): PIN validity (25%), Locality match (25%), City/District/State consistency (20%), Parsing completeness (15%), Fuzzy match quality (15%) | P0 |
| FR-48 | Score breakdown per component for audit | P0 |
| FR-49 | Tier labels: HIGH (≥85), MEDIUM (60–84), LOW (40–59), UNVERIFIED (<40) | P0 |
| FR-50 | Flag records needing manual review (LOW/UNVERIFIED) | P0 |

### 2.10 Audit Trail & Processing Metadata

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-51 | Create immutable processing job record: job_id, user_id, filename, row_count, column_map, started_at, completed_at, status | P0 |
| FR-52 | Store per-record transformation log: original_value, normalized_value, parsed_components, matched_entity, match_score, action_taken | P0 |
| FR-53 | Track processing time per stage (profiling, parsing, matching, enrichment, scoring) | P1 |
| FR-54 | Export audit trail as CSV/Parquet for compliance | P1 |

### 2.11 Quality Reports (Before vs After)

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-55 | Pre-processing profile: null %, format violations, duplicate PINs, out-of-range PINs | P0 |
| FR-56 | Post-processing profile: fill rate, standardization rate, enrichment rate, confidence distribution | P0 |
| FR-57 | Delta report: records improved, records degraded, records unchanged | P0 |
| FR-58 | Visual summary: bar charts, histograms, sankey flow (before→after tiers) | P1 |
| FR-59 | Export report as PDF + JSON + CSV | P1 |

### 2.12 Export & Delivery

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-60 | Export enriched dataset: CSV, Excel (.xlsx), Parquet | P0 |
| FR-61 | Include original columns + enriched columns + confidence columns | P0 |
| FR-62 | Optional: export only HIGH confidence records | P1 |
| FR-63 | Optional: export review queue (LOW/UNVERIFIED) as separate file | P1 |
| FR-64 | Streaming export for >1M rows (chunked download) | P1 |

### 2.13 Batch Processing (10M Records)

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-65 | Chunk large files into configurable batches (default 50k rows) | P0 |
| FR-66 | Process batches in parallel via Celery workers (horizontal scaling) | P0 |
| FR-67 | Progress tracking: real-time % complete, rows/sec, ETA | P0 |
| FR-68 | Resume failed jobs from last completed batch (checkpointing) | P1 |
| FR-69 | Resource limits: max memory/worker, max concurrent workers | P1 |

### 2.14 Interactive Analytics Dashboard

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-70 | Overview: total records, enrichment rate, confidence distribution, processing time | P0 |
| FR-71 | Geographic heatmap: record density by State/District/City (choropleth) | P1 |
| FR-72 | Quality trends: completeness by column, top mismatch patterns | P1 |
| FR-73 | Drill-down: click State → District → City → Locality | P1 |
| FR-74 | Filter by: confidence tier, date range, source file, processing job | P1 |
| FR-75 | Export dashboard snapshot as image/PDF | P2 |

### 2.15 Geography Data Management

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-76 | Admin CLI to download/refresh: India Post PIN CSV, Census village/town CSV, OSM India PBF | P0 |
| FR-77 | Build search indexes: PIN→Localities (BK-tree / Trie), Locality→PIN (inverted index) | P0 |
| FR-78 | Build PostGIS tables: state/district/city boundaries for choropleth | P1 |
| FR-79 | Version geography datasets; support rollback | P1 |

---

## 3. Non-Functional Requirements

### 3.1 Performance

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-01 | Single-record processing latency (parse + match + enrich) | < 50 ms |
| NFR-02 | Batch throughput (10M records, 8 workers, 32 GB RAM) | > 100k records/min |
| NFR-03 | API response time (job status, file upload) | < 500 ms p95 |
| NFR-04 | Dashboard query latency (aggregations on 10M rows) | < 2 s |
| NFR-05 | File upload (2 GB) | < 5 min on 100 Mbps |

### 3.2 Scalability

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-06 | Horizontal worker scaling (Celery) | Up to 32 workers |
| NFR-07 | Redis cache for fuzzy match results | 10M keys, TTL 24h |
| NFR-08 | PostgreSQL partitioning by job_id for audit tables | 10M+ rows |
| NFR-09 | Parquet columnar storage for enriched exports | Compression > 5x |

### 3.3 Reliability

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-10 | Job success rate (excluding bad input data) | ≥ 99.9% |
| NFR-11 | Worker crash recovery (acknowledgment + retry) | Auto-retry 3x |
| NFR-12 | Data integrity: zero record loss during processing | Guaranteed |
| NFR-13 | Backup: daily PostgreSQL dump, weekly geography DB snapshot | Automated |

### 3.4 Security

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-14 | Authentication: JWT (access + refresh), HttpOnly cookies | Standard |
| NFR-15 | Authorization: RBAC (Admin, Analyst, Viewer) | Required |
| NFR-16 | File upload: virus scan (ClamAV), size limit, type validation | Mandatory |
| NFR-17 | PII handling: patient_id hashed in logs, address data encrypted at rest (AES-256) | Mandatory |
| NFR-18 | Audit log: all user actions, data exports, config changes | Immutable |
| NFR-19 | No PHI in geography datasets (only public admin boundaries) | Guaranteed |

### 3.5 Maintainability

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-20 | Code coverage (unit + integration) | ≥ 85% |
| NFR-21 | API documentation (OpenAPI/Swagger) | 100% endpoints |
| NFR-22 | Architecture decision records (ADR) for major choices | Required |
| NFR-23 | Dependency updates: monthly automated PR (Dependabot) | Configured |

### 3.6 Usability

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-24 | Upload-to-results flow: ≤ 5 clicks for standard dataset | UX goal |
| NFR-25 | Error messages: actionable, non-technical language | Required |
| NFR-26 | Dark/light theme, responsive (≥ 1024px) | Required |

### 3.7 Offline-First Operation

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-27 | Zero external API calls during processing | Mandatory |
| NFR-28 | All geography data stored in PostgreSQL/PostGIS + Redis | Mandatory |
| NFR-29 | One-time dataset download script (India Post, Census, OSM) | Provided |
| NFR-30 | Air-gapped deployment supported (Docker images + data volumes) | Required |

---

## 4. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              GEOCARE AI ARCHITECTURE                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌────────────┐ │
│  │   FRONTEND   │    │   BACKEND    │    │  GEOGRAPHY   │    │  MESSAGE   │ │
│  │  (Next.js)   │◄───│  (FastAPI)   │◄───│  INTELLIGENCE│    │   QUEUE    │ │
│  │              │    │              │    │   ENGINE     │    │  (Redis)   │ │
│  │  - Upload    │    │  - Auth      │    │              │    │            │ │
│  │  - Profile   │    │  - Jobs      │    │  - PIN Index │    │  ┌──────┐  │ │
│  │  - Dashboard │    │  - Files     │    │  - Locality  │    │  │Celery│  │ │
│  │  - Reports   │    │  - Reports   │    │  - Fuzzy     │    │  │Worker│  │ │
│  │  - Export    │    │  - Export    │    │  - Parser    │    │  └──────┘  │ │
│  └──────────────┘    └──────┬───────┘    └──────┬───────┘    └────────────┘ │
│                             │                     │                           │
│                    ┌────────▼────────┐   ┌───────▼───────┐                   │
│                    │   POSTGRESQL    │   │    REDIS      │                   │
│                    │   + POSTGIS     │   │  (Cache/Queue)│                   │
│                    │                 │   │               │                   │
│                    │  - Jobs         │   │  - Fuzzy cache│                   │
│                    │  - Files        │   │  - Session    │                   │
│                    │  - Audit log    │   │  - Rate limit │                   │
│                    │  - Geography    │   │               │                   │
│                    └─────────────────┘   └───────────────┘                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.1 Module Boundaries (Clean Architecture)

| Layer | Responsibility | Technologies |
|-------|---------------|--------------|
| **Domain** | Entities, value objects, domain events, repository interfaces | Python `dataclasses`, `pydantic`, `abc` |
| **Application** | Use cases, DTOs, ports (interfaces), orchestration | FastAPI routers, Pydantic schemas |
| **Infrastructure** | DB repos, external libs adapters, geography indexes | SQLAlchemy, Polars, RapidFuzz, libpostal, PostGIS |
| **Presentation** | API endpoints, WebSocket, CLI | FastAPI, Next.js, WebSockets |

---

## 5. Data Models (Logical)

### 5.1 Core Entities

```python
# Domain entities (simplified)

class ProcessingJob:
    id: UUID
    user_id: UUID
    filename: str
    original_row_count: int
    column_mapping: ColumnMapping
    status: JobStatus  # PENDING, PROFILING, PROCESSING, COMPLETED, FAILED, CANCELLED
    started_at: datetime
    completed_at: Optional[datetime]
    error_message: Optional[str]
    stats: JobStats

class ColumnMapping:
    patient_id: Optional[str]
    address_line_1: Optional[str]
    address_line_2: Optional[str]
    landmark: Optional[str]
    pincode: Optional[str]
    city: Optional[str]
    district: Optional[str]
    state: Optional[str]
    country: Optional[str]

class AddressRecord:
    id: UUID
    job_id: UUID
    row_index: int
    patient_id_hash: str  # SHA256(patient_id + salt)
    original_address: str
    normalized_address: str
    parsed_components: ParsedAddress
    enriched_components: EnrichedAddress
    confidence: ConfidenceScore
    tier: ConfidenceTier
    audit_log: List[AuditEntry]

class ParsedAddress:
    house_number: Optional[str]
    street: Optional[str]
    locality: Optional[str]
    sublocality: Optional[str]
    village: Optional[str]
    taluk: Optional[str]
    city: Optional[str]
    district: Optional[str]
    state: Optional[str]
    pincode: Optional[str]
    country: str = "India"

class EnrichedAddress:
    canonical_locality: Optional[str]
    canonical_city: Optional[str]
    canonical_district: Optional[str]
    canonical_state: Optional[str]
    canonical_pincode: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]

class ConfidenceScore:
    overall: int  # 0-100
    pincode_validity: int
    locality_match: int
    hierarchy_consistency: int
    parsing_completeness: int
    fuzzy_quality: int

class ConfidenceTier(Enum):
    HIGH = "HIGH"           # >= 85
    MEDIUM = "MEDIUM"       # 60-84
    LOW = "LOW"             # 40-59
    UNVERIFIED = "UNVERIFIED"  # < 40
```

### 5.2 Geography Reference Data

| Table | Source | Approx. Rows | Key Columns |
|-------|--------|--------------|-------------|
| `pincode_directory` | India Post | 19,000 | pincode, office_name, district, state, taluk, delivery_status |
| `pincode_localities` | India Post + OSM | 150,000 | pincode, locality, locality_type |
| `locality_dictionary` | India Post + OSM + Census | 1.5M | canonical_name, aliases[], state, district, pincode[] |
| `census_hierarchy` | Census 2011/2021 | 650K | state_code, district_code, subdistrict_code, village_code, name, level |
| `osm_boundaries` | OSM India | 36 (states) + 700+ (districts) | admin_level, name, geometry (PostGIS) |

---

## 6. API Specification (High-Level)

### 6.1 Authentication
- `POST /auth/login` – email/password → JWT pair
- `POST /auth/refresh` – refresh token → new access token
- `POST /auth/logout` – revoke refresh token

### 6.2 File Management
- `POST /files/upload` – multipart upload → returns `file_id`
- `GET /files/{file_id}/profile` – data profiling results
- `POST /files/{file_id}/confirm-columns` – user confirms column mapping

### 6.3 Job Management
- `POST /jobs` – create processing job from profiled file
- `GET /jobs/{job_id}` – job status + progress
- `GET /jobs/{job_id}/stream` – Server-Sent Events for real-time progress
- `POST /jobs/{job_id}/cancel` – cancel running job
- `POST /jobs/{job_id}/retry` – retry failed job

### 6.4 Results & Export
- `GET /jobs/{job_id}/report` – quality report (JSON)
- `GET /jobs/{job_id}/export?format=csv|xlsx|parquet` – streaming download
- `GET /jobs/{job_id}/audit` – audit trail export

### 6.5 Dashboard
- `GET /dashboard/overview` – aggregate stats
- `GET /dashboard/geography?level=state|district|city` – choropleth data
- `GET /dashboard/quality` – quality trends
- `GET /dashboard/jobs` – recent jobs list

### 6.6 Geography Admin (Admin only)
- `POST /admin/geography/download` – trigger dataset download
- `POST /admin/geography/build-indexes` – rebuild search indexes
- `GET /admin/geography/status` – dataset versions, index status

---

## 7. Processing Pipeline (Detailed Flow)

```
┌─────────────┐
│  UPLOAD     │  User uploads CSV/Excel
└──────┬──────┘
       ▼
┌─────────────┐
│  PROFILE    │  Polars: read sample (10k rows), infer schema,
│             │  detect address columns, compute stats
└──────┬──────┘
       ▼ (user confirms mapping)
┌─────────────┐
│  CHUNK      │  Split into batches (50k rows), persist to object store
└──────┬──────┘
       ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  PARSE      │────►│  MATCH      │────►│  ENRICH     │
│  (libpostal)│     │  (RapidFuzz)│     │  (PIN/Dict) │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                                ▼
                                         ┌─────────────┐
                                         │  SCORE      │
                                         │  (Weighted) │
                                         └──────┬──────┘
                                                ▼
                                         ┌─────────────┐
                                         │  PERSIST    │
                                         │  (Audit +   │
                                         │   Enriched) │
                                         └─────────────┘
```

**Parallelization:** Each chunk processed independently by Celery worker.  
**Checkpointing:** Job tracks completed chunk IDs; retry resumes from last incomplete.

---

## 8. Geography Intelligence Engine – Technical Design

### 8.1 PIN Code Index
- **Structure:** `dict[pincode] -> PincodeRecord` (loaded in memory, ~19k entries)
- **Reverse Index:** `dict[locality_lower] -> List[pincode]` (inverted index)
- **Validation:** Regex `^[1-8][0-9]{5}$` + existence in directory

### 8.2 Locality Fuzzy Index
- **Primary:** BK-Tree (Burkhard-Keller) for Levenshtein distance < 3
- **Secondary:** Trie for prefix matching
- **Tertiary:** RapidFuzz token_set_ratio for multi-word localities
- **Cache:** Redis `locality_match:{query_hash}` → `List[MatchResult]` (TTL 24h)

### 8.3 libpostal Integration
- Use `postal.parser.parse_address()` with custom `libpostal` data directory
- Train/extend with Indian address patterns (add to `libpostal` training data)
- Output components mapped to `ParsedAddress` domain model

### 8.4 PostGIS Boundaries
- Import OSM admin boundaries (level 4, 6, 8, 10) via `osm2pgsql`
- Materialized views for choropleth: `state_geom`, `district_geom`, `city_geom`
- Spatial index (GiST) on geometry columns

---

## 9. Deployment Architecture

### 9.1 Docker Compose Services (Development)

| Service | Image | Ports | Volumes |
|---------|-------|-------|---------|
| `postgres` | postgis/postgis:16-3.4 | 5432 | pgdata |
| `redis` | redis:7-alpine | 6379 | redis-data |
| `backend` | geocare-backend:dev | 8000 | ./backend:/app |
| `celery-worker` | geocare-backend:dev | – | ./backend:/app |
| `celery-beat` | geocare-backend:dev | – | ./backend:/app |
| `frontend` | geocare-frontend:dev | 3000 | ./frontend:/app |
| `nginx` | nginx:alpine | 80/443 | ./nginx.conf |

### 9.2 Production (Kubernetes / Docker Swarm)
- Backend: HPA (CPU > 70% → scale workers)
- Celery: KEDA scaling on queue length
- PostgreSQL: Patroni HA cluster
- Redis: Sentinel/Cluster mode
- Object storage: MinIO / S3 for chunked files
- Monitoring: Prometheus + Grafana + Loki

---

## 10. Testing Strategy

| Layer | Tool | Coverage Target |
|-------|------|-----------------|
| Unit (Domain) | pytest | 90% |
| Unit (Application) | pytest + httpx | 85% |
| Integration (API) | pytest + testcontainers | 80% |
| Integration (Pipeline) | pytest + real data samples | 70% |
| E2E (Frontend) | Playwright | Critical paths |
| Performance | locust | 100k records baseline |
| Geography Accuracy | Custom eval set (10k labeled) | ≥ 95% tier accuracy |

### 10.1 Test Data
- Synthetic patient datasets (1k, 10k, 100k, 1M rows)
- Golden set: 10,000 manually verified Indian addresses across 28 states
- Edge cases: misspellings, missing components, bilingual, obsolete PINs

---

## 11. Project Structure (Monorepo)

```
geocare-ai/
├── .github/
│   └── workflows/
├── docs/
│   ├── adr/
│   └── architecture/
├── docker/
│   ├── docker-compose.yml
│   ├── docker-compose.prod.yml
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   └── nginx.conf
├── backend/
│   ├── src/
│   │   ├── geocare/
│   │   │   ├── domain/           # Entities, value objects, events, repo interfaces
│   │   │   ├── application/      # Use cases, DTOs, ports
│   │   │   ├── infrastructure/   # Repos, adapters, geography engine
│   │   │   │   ├── persistence/
│   │   │   │   ├── geography/
│   │   │   │   │   ├── pincode_index.py
│   │   │   │   │   ├── locality_fuzzy.py
│   │   │   │   │   ├── parser_adapter.py
│   │   │   │   │   └── postgis_repo.py
│   │   │   │   └── task_queue/
│   │   │   ├── presentation/     # FastAPI routers, schemas, websockets
│   │   │   └── config/
│   │   └── main.py
│   ├── tests/
│   ├── pyproject.toml
│   └── alembic/
├── frontend/
│   ├── src/
│   │   ├── app/                  # Next.js App Router
│   │   ├── components/           # shadcn/ui + custom
│   │   ├── hooks/
│   │   ├── lib/
│   │   └── types/
│   ├── tests/                    # Playwright
│   ├── package.json
│   └── tailwind.config.ts
├── geography-data/               # Downloaded datasets (gitignored)
│   ├── india_post/
│   ├── census/
│   └── osm/
├── scripts/
│   ├── download_geography.py
│   ├── build_indexes.py
│   └── evaluate_accuracy.py
├── Makefile
├── README.md
└── SRS.md                        # This document
```

---

## 12. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| libpostal parsing accuracy for Indian addresses | Medium | High | Custom training data; fallback to rule-based parser |
| Fuzzy matching false positives (similar locality names) | Medium | High | Multi-signal scoring (PIN + district + state context) |
| 10M record memory pressure | Medium | High | Polars streaming + chunked processing; configurable batch size |
| Geography data staleness (PIN codes change) | Low | Medium | Quarterly refresh pipeline; versioned datasets |
| PostGIS performance on choropleth queries | Low | Medium | Pre-aggregated materialized views; tile caching |
| PII leakage in logs/audit | Low | Critical | Structured logging with PII scrubber; encryption at rest |

---

## 13. Acceptance Criteria (Phase 1 Complete)

- [ ] SRS document reviewed and approved by stakeholders
- [ ] Functional requirements traceability matrix created
- [ ] Non-functional requirements validated against infrastructure capacity
- [ ] Architecture decision records (ADRs) drafted for:
  - [ ] Polars vs Pandas for processing
  - [ ] Celery vs RQ for task queue
  - [ ] libpostal vs custom parser
  - [ ] PostgreSQL vs ClickHouse for analytics
- [ ] Geography data sources verified and download scripts tested
- [ ] Project structure scaffolded with baseline tooling (lint, type-check, test)

---

## 14. Sign-Off

| Role | Name | Signature | Date |
|------|------|-----------|------|
| Product Owner | | | |
| Lead Architect | | | |
| Engineering Lead | | | |
| QA Lead | | | |
| Data Privacy Officer | | | |

---

**End of SRS v1.0**