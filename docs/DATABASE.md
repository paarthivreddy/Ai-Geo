# Database Design

## GeoCare AI – India Patient Address Intelligence Platform

**Version:** 1.0  
**Status:** Draft  
**Date:** 2025-07-17  
**Classification:** Internal – Enterprise Use Only

---

## 1. Overview

### 1.1 Database Strategy

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| **Primary DB** | PostgreSQL 16 + PostGIS 3.4 | ACID compliance, mature spatial extension, JSONB support |
| **Cache/Queue** | Redis 7 Cluster | Sub-ms latency, pub/sub, sorted sets for rate limiting |
| **Spatial DB** | Separate PostGIS instance (OSM boundaries) | Isolate heavy spatial workloads, independent scaling |
| **ORM** | SQLAlchemy 2.0 (async) | Type-safe, async support, Alembic migrations |
| **Partitioning** | Hash partition on `job_id` (patient_records) | Efficient job-scoped queries, parallel scans |
| **Migration Tool** | Alembic (versioned, reversible) | Industry standard, integrates with SQLAlchemy |

### 1.2 Database Instances

```mermaid
graph TB
    subgraph Primary["Primary PostgreSQL Cluster"]
        PG_PRIMARY[(Primary\nRead/Write)]
        PG_REPLICA1[(Replica 1\nRead)]
        PG_REPLICA2[(Replica 2\nRead)]
        PG_PRIMARY -->|Async Replication| PG_REPLICA1
        PG_PRIMARY -->|Async Replication| PG_REPLICA2
    end

    subgraph Spatial["OSM PostGIS Instance"]
        OSM_PRIMARY[(OSM Primary\nRead/Write)]
        OSM_REPLICA[(OSM Replica\nRead)]
        OSM_PRIMARY -->|Async Replication| OSM_REPLICA
    end

    subgraph Cache["Redis Cluster (3 Shards)"]
        REDIS_S1[(Shard 1)]
        REDIS_S2[(Shard 2)]
        REDIS_S3[(Shard 3)]
    end

    API[FastAPI App] --> PG_PRIMARY
    API --> PG_REPLICA1
    API --> PG_REPLICA2
    WORKER[Celery Workers] --> PG_PRIMARY
    WORKER --> OSM_PRIMARY
    WORKER --> REDIS_S1
    WORKER --> REDIS_S2
    WORKER --> REDIS_S3
```

---

## 2. Core Schema (Primary Database)

### 2.1 Users & Authentication

```sql
-- Enum types
CREATE TYPE user_role AS ENUM ('admin', 'analyst', 'viewer');
CREATE TYPE user_status AS ENUM ('active', 'inactive', 'locked');

-- Users table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,  -- bcrypt
    full_name VARCHAR(255) NOT NULL,
    role user_role NOT NULL DEFAULT 'viewer',
    status user_status NOT NULL DEFAULT 'active',
    salt VARCHAR(32) NOT NULL,  -- for patient_id hashing
    last_login_at TIMESTAMPTZ,
    failed_login_attempts INT DEFAULT 0,
    locked_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_status ON users(status) WHERE status = 'active';

-- Trigger for updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END $$;

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
```

### 2.2 Processing Jobs

```sql
-- Job status enum
CREATE TYPE job_status AS ENUM (
    'pending', 'profiling', 'mapping', 'queued', 
    'processing', 'completed', 'failed', 'cancelled'
);

-- Column mapping stored as JSONB
CREATE TYPE column_mapping AS (
    patient_id VARCHAR,
    address_line_1 VARCHAR,
    address_line_2 VARCHAR,
    landmark VARCHAR,
    pincode VARCHAR,
    city VARCHAR,
    district VARCHAR,
    state VARCHAR,
    country VARCHAR
);

-- Processing jobs table
CREATE TABLE processing_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    filename VARCHAR(500) NOT NULL,
    original_file_path VARCHAR(1000),  -- S3/local path
    parquet_file_path VARCHAR(1000),   -- Converted Parquet chunks path
    total_rows INT NOT NULL DEFAULT 0,
    total_columns INT NOT NULL DEFAULT 0,
    column_mapping JSONB NOT NULL DEFAULT '{}',
    detected_address_columns TEXT[] DEFAULT '{}',
    status job_status NOT NULL DEFAULT 'pending',
    progress_pct REAL NOT NULL DEFAULT 0.0,
    processed_rows INT NOT NULL DEFAULT 0,
    succeeded_rows INT NOT NULL DEFAULT 0,
    failed_rows INT NOT NULL DEFAULT 0,
    manual_review_rows INT NOT NULL DEFAULT 0,
    chunk_size INT NOT NULL DEFAULT 50000,
    total_chunks INT NOT NULL DEFAULT 0,
    completed_chunks INT[] DEFAULT '{}',
    failed_chunks INT[] DEFAULT '{}',
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Job stats (quality metrics) - populated on completion
CREATE TABLE job_quality_stats (
    job_id UUID PRIMARY KEY REFERENCES processing_jobs(id) ON DELETE CASCADE,
    -- Pre-processing metrics
    total_records INT,
    complete_addresses_before INT,
    missing_pincode_before INT,
    missing_locality_before INT,
    missing_city_before INT,
    missing_district_before INT,
    missing_state_before INT,
    invalid_addresses_before INT,
    duplicate_addresses_before INT,
    overall_quality_before REAL,
    -- Post-processing metrics
    pincodes_added INT,
    cities_added INT,
    districts_added INT,
    states_added INT,
    spell_corrections INT,
    improved_records INT,
    manual_review_records INT,
    final_quality_score REAL,
    improvement_percentage REAL,
    -- Confidence distribution
    confidence_high INT DEFAULT 0,
    confidence_medium INT DEFAULT 0,
    confidence_low INT DEFAULT 0,
    confidence_unverified INT DEFAULT 0,
    -- Processing time breakdown (seconds)
    profiling_time REAL,
    processing_time REAL,
    reporting_time REAL,
    export_time REAL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_jobs_user_status ON processing_jobs(user_id, status);
CREATE INDEX idx_jobs_created_at ON processing_jobs(created_at DESC);
CREATE INDEX idx_jobs_status ON processing_jobs(status) WHERE status IN ('processing', 'queued');

CREATE TRIGGER trg_jobs_updated_at
    BEFORE UPDATE ON processing_jobs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
```

### 2.3 Job Chunks (Batch Tracking)

```sql
-- Chunk status enum
CREATE TYPE chunk_status AS ENUM ('pending', 'processing', 'completed', 'failed');

-- Job chunks table
CREATE TABLE job_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES processing_jobs(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    storage_path VARCHAR(1000) NOT NULL,  -- S3/local path to Parquet chunk
    row_count INT NOT NULL DEFAULT 0,
    status chunk_status NOT NULL DEFAULT 'pending',
    retry_count INT NOT NULL DEFAULT 0,
    max_retries INT NOT NULL DEFAULT 3,
    error_message TEXT,
    worker_id VARCHAR(100),  -- Celery worker hostname
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (job_id, chunk_index)
);

CREATE INDEX idx_chunks_job_status ON job_chunks(job_id, status);
CREATE INDEX idx_chunks_worker ON job_chunks(worker_id) WHERE status = 'processing';
```

### 2.4 Patient Records (Partitioned)

```sql
-- Review status enum
CREATE TYPE review_status AS ENUM ('auto', 'needs_review', 'manual_verified', 'rejected');
CREATE TYPE confidence_tier AS ENUM ('high', 'medium', 'low', 'unverified');
CREATE TYPE match_method AS ENUM ('exact', 'fuzzy', 'inferred', 'manual');

-- Confidence score structure (JSONB)
-- {
--   "overall": 85,
--   "pincode_validity": 100,
--   "locality_match": 85,
--   "hierarchy_consistency": 90,
--   "parsing_completeness": 70,
--   "fuzzy_quality": 80,
--   "method": "fuzzy",
--   "tier": "high"
-- }

-- Patient records table - HASH partitioned by job_id
CREATE TABLE patient_records (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES processing_jobs(id) ON DELETE CASCADE,
    row_index INT NOT NULL,
    patient_id_hash VARCHAR(64) NOT NULL,  -- SHA256(patient_id + job_salt)
    
    -- Original input
    original_address JSONB NOT NULL DEFAULT '{}',
    
    -- Normalized address (after cleaning)
    normalized_address JSONB NOT NULL DEFAULT '{}',
    
    -- Parsed components (libpostal output)
    parsed_address JSONB NOT NULL DEFAULT '{}',
    
    -- Final enriched address
    enriched_address JSONB NOT NULL DEFAULT '{}',
    
    -- Confidence scoring
    confidence_score JSONB NOT NULL DEFAULT '{}',
    confidence_tier confidence_tier NOT NULL DEFAULT 'unverified',
    match_method match_method NOT NULL DEFAULT 'manual',
    
    -- Review workflow
    review_status review_status NOT NULL DEFAULT 'auto',
    reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    review_notes TEXT,
    
    -- Geometry for spatial queries (choropleth)
    geometry GEOGRAPHY(POINT, 4326),
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    PRIMARY KEY (job_id, id)
) PARTITION BY HASH (job_id);

-- Create 16 partitions (adjust based on expected concurrent jobs)
DO $$
DECLARE i INT;
BEGIN
    FOR i IN 0..15 LOOP
        EXECUTE format(
            'CREATE TABLE patient_records_p%s PARTITION OF patient_records FOR VALUES WITH (MODULUS 16, REMAINDER %s)',
            i, i
        );
    END LOOP;
END $$;

-- Indexes (created on each partition automatically)
-- Note: In PostgreSQL, indexes on partitioned tables are created on each partition
CREATE INDEX idx_patient_records_job_id ON patient_records(job_id);
CREATE INDEX idx_patient_records_review_status ON patient_records(review_status) WHERE review_status != 'auto';
CREATE INDEX idx_patient_records_confidence_tier ON patient_records(confidence_tier);
CREATE INDEX idx_patient_records_geometry ON patient_records USING GIST (geometry);
CREATE INDEX idx_patient_records_patient_hash ON patient_records(patient_id_hash);

-- Partial index for review queue
CREATE INDEX idx_patient_records_review_queue 
    ON patient_records(job_id, review_status, confidence_tier) 
    WHERE review_status IN ('needs_review', 'manual_verified');

-- Trigger for updated_at on each partition
-- (Applied via migration script per partition)
```

### 2.5 Audit Entries

```sql
-- Processing method enum
CREATE TYPE processing_method AS ENUM (
    'normalization', 'parsing', 'pin_resolution', 
    'locality_match', 'spell_correction', 'hierarchy_enrichment',
    'validation_correction', 'manual_override'
);

-- Data source enum
CREATE TYPE data_source AS ENUM (
    'india_post', 'osm', 'census', 'libpostal', 'rapidfuzz', 'manual', 'inferred'
);

-- Audit entries table
CREATE TABLE audit_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    record_id UUID NOT NULL,
    job_id UUID NOT NULL,
    field_name VARCHAR(100) NOT NULL,
    old_value TEXT,
    new_value TEXT,
    processing_method processing_method NOT NULL,
    confidence INT NOT NULL CHECK (confidence BETWEEN 0 AND 100),
    source_dataset data_source NOT NULL,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Partition audit entries by job_id for efficient cleanup
ALTER TABLE audit_entries 
    SET (autovacuum_vacuum_scale_factor = 0.05);

CREATE INDEX idx_audit_record_id ON audit_entries(record_id);
CREATE INDEX idx_audit_job_id ON audit_entries(job_id);
CREATE INDEX idx_audit_field ON audit_entries(field_name);
CREATE INDEX idx_audit_created_at ON audit_entries(created_at DESC);
```

---

## 3. Geography Reference Data

### 3.1 PIN Code Directory (India Post)

```sql
-- Office type enum
CREATE TYPE office_type AS ENUM ('head', 'sub', 'branch');
CREATE TYPE delivery_status AS ENUM ('delivery', 'non_delivery');

CREATE TABLE pincode_directory (
    pincode CHAR(6) PRIMARY KEY,
    office_name VARCHAR(255) NOT NULL,
    office_type office_type NOT NULL,
    delivery_status delivery_status NOT NULL,
    district VARCHAR(100) NOT NULL,
    state VARCHAR(100) NOT NULL,
    taluk VARCHAR(100),
    circle VARCHAR(100),
    region VARCHAR(100),
    division VARCHAR(100),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    localities TEXT[],  -- Array of locality names served by this PIN
    source_version VARCHAR(50) NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    CONSTRAINT valid_pincode CHECK (pincode ~ '^[1-8][0-9]{5}$')
);

CREATE INDEX idx_pincode_district_state ON pincode_directory(district, state);
CREATE INDEX idx_pincode_taluk ON pincode_directory(taluk);
CREATE INDEX idx_pincode_geo ON pincode_directory(latitude, longitude) 
    WHERE latitude IS NOT NULL AND longitude IS NOT NULL;
```

### 3.2 Locality Dictionary (India Post + OSM + Census)

```sql
-- Source enum
CREATE TYPE locality_source AS ENUM ('india_post', 'osm', 'census', 'merged');

CREATE TABLE locality_dictionary (
    id BIGSERIAL PRIMARY KEY,
    canonical_name VARCHAR(255) NOT NULL,
    aliases TEXT[] DEFAULT '{}',  -- Alternative spellings/names
    pincode CHAR(6) NOT NULL REFERENCES pincode_directory(pincode),
    city VARCHAR(100) NOT NULL,
    district VARCHAR(100) NOT NULL,
    state VARCHAR(100) NOT NULL,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    population BIGINT,
    source locality_source NOT NULL,
    source_version VARCHAR(50),
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    CONSTRAINT valid_coords CHECK (
        (latitude IS NULL AND longitude IS NULL) OR
        (latitude BETWEEN 6.0 AND 38.0 AND longitude BETWEEN 68.0 AND 98.0)
    )
);

-- Critical indexes for fuzzy matching
CREATE INDEX idx_locality_canonical ON locality_dictionary(canonical_name);
CREATE INDEX idx_locality_aliases_gin ON locality_dictionary USING GIN (aliases);
CREATE INDEX idx_locality_pincode ON locality_dictionary(pincode);
CREATE INDEX idx_locality_city_district ON locality_dictionary(city, district);
CREATE INDEX idx_locality_state ON locality_dictionary(state);
CREATE INDEX idx_locality_geo ON locality_dictionary(latitude, longitude) 
    WHERE latitude IS NOT NULL;

-- Trigram index for pg_trgm fuzzy search (optional fallback)
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX idx_locality_canonical_trgm ON locality_dictionary 
    USING GIN (canonical_name gin_trgm_ops);
CREATE INDEX idx_locality_aliases_trgm ON locality_dictionary 
    USING GIN (aliases gin_trgm_ops);
```

### 3.3 Census Hierarchy

```sql
CREATE TABLE census_hierarchy (
    state_code CHAR(2) PRIMARY KEY,
    state_name VARCHAR(100) NOT NULL,
    district_code CHAR(4),
    district_name VARCHAR(100),
    subdistrict_code CHAR(6),
    subdistrict_name VARCHAR(100),
    village_code CHAR(8),
    village_name VARCHAR(255),
    level VARCHAR(20) NOT NULL,  -- 'State', 'District', 'Sub-district', 'Village', 'Town'
    population BIGINT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    source_version VARCHAR(50),
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_census_district ON census_hierarchy(district_code);
CREATE INDEX idx_census_subdistrict ON census_hierarchy(subdistrict_code);
CREATE INDEX idx_census_village ON census_hierarchy(village_code);
CREATE INDEX idx_census_names ON census_hierarchy(state_name, district_name, village_name);
```

### 3.4 Dataset Versions (Tracking)

```sql
CREATE TABLE geography_dataset_versions (
    id BIGSERIAL PRIMARY KEY,
    dataset_name VARCHAR(50) NOT NULL,  -- 'pincode', 'locality', 'census', 'osm'
    version VARCHAR(50) NOT NULL,
    source_url TEXT,
    checksum_sha256 VARCHAR(64),
    row_count BIGINT,
    status VARCHAR(20) NOT NULL DEFAULT 'loaded',  -- 'loading', 'loaded', 'failed', 'archived'
    error_message TEXT,
    loaded_by UUID REFERENCES users(id),
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    activated_at TIMESTAMPTZ,
    archived_at TIMESTAMPTZ,
    
    UNIQUE (dataset_name, version)
);

CREATE INDEX idx_dataset_active ON geography_dataset_versions(dataset_name, status) 
    WHERE status = 'loaded';
```

---

## 4. OSM PostGIS Database (Separate Instance)

### 4.1 Admin Boundaries

```sql
-- In OSM database (separate connection)
CREATE SCHEMA osm;

CREATE TABLE osm.admin_boundaries (
    id BIGSERIAL PRIMARY KEY,
    osm_id BIGINT NOT NULL,
    admin_level SMALLINT NOT NULL,  -- 4=state, 6=district, 8=city/town, 10=village
    name TEXT NOT NULL,
    name_en TEXT,
    name_hi TEXT,  -- Devanagari
    tags JSONB,
    geom GEOMETRY(MULTIPOLYGON, 4326) NOT NULL,
    way_area DOUBLE PRECISION,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_osm_admin_level ON osm.admin_boundaries(admin_level);
CREATE INDEX idx_osm_name ON osm.admin_boundaries(name);
CREATE INDEX idx_osm_name_en ON osm.admin_boundaries(name_en);
CREATE INDEX idx_osm_geom ON osm.admin_boundaries USING GIST (geom);

-- Materialized views for dashboard choropleth
CREATE MATERIALIZED VIEW osm.state_boundaries AS
SELECT osm_id, name, name_en, geom
FROM osm.admin_boundaries
WHERE admin_level = 4;

CREATE MATERIALIZED VIEW osm.district_boundaries AS
SELECT osm_id, name, name_en, geom
FROM osm.admin_boundaries
WHERE admin_level = 6;

CREATE UNIQUE INDEX idx_state_boundaries_osm_id ON osm.state_boundaries(osm_id);
CREATE UNIQUE INDEX idx_district_boundaries_osm_id ON osm.district_boundaries(osm_id);
CREATE INDEX idx_state_boundaries_geom ON osm.state_boundaries USING GIST (geom);
CREATE INDEX idx_district_boundaries_geom ON osm.district_boundaries USING GIST (geom);

-- Refresh function
CREATE OR REPLACE FUNCTION osm.refresh_choropleth_views()
RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY osm.state_boundaries;
    REFRESH MATERIALIZED VIEW CONCURRENTLY osm.district_boundaries;
END $$;
```

### 4.2 Locality Points (OSM POIs)

```sql
CREATE TABLE osm.locality_points (
    id BIGSERIAL PRIMARY KEY,
    osm_id BIGINT NOT NULL,
    name TEXT NOT NULL,
    name_en TEXT,
    place_type TEXT,  -- 'suburb', 'neighbourhood', 'village', 'town', 'city'
    tags JSONB,
    geom GEOMETRY(POINT, 4326) NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_osm_locality_name ON osm.locality_points(name);
CREATE INDEX idx_osm_locality_place ON osm.locality_points(place_type);
CREATE INDEX idx_osm_locality_geom ON osm.locality_points USING GIST (geom);
```

---

## 5. Redis Schema

### 5.1 Key Patterns

| Pattern | Type | TTL | Description |
|---------|------|-----|-------------|
| `job:{job_id}:status` | String | 24h | Current job status |
| `job:{job_id}:progress` | Hash | 24h | `processed`, `total`, `current_batch`, `pct`, `rate`, `eta` |
| `job:{job_id}:chunks` | Set | 24h | Completed chunk indices |
| `job:{job_id}:stream` | Pub/Sub | - | SSE progress channel |
| `fuzzy:{query_hash}` | String (JSON) | 24h | Cached fuzzy match results |
| `worker:{worker_id}:heartbeat` | String | 60s | Worker liveness timestamp |
| `rate_limit:{user_id}:{endpoint}` | String | 60s | API rate limit counter |
| `session:{session_id}` | Hash | 7d | User session data |
| `geo:index:version` | String | - | Current geography dataset version |

### 5.2 Progress Hash Structure

```redis
HSET job:{job_id}:progress \
    processed 125000 \
    total 500000 \
    current_batch 3 \
    total_batches 10 \
    pct 25.0 \
    rate 1250.5 \
    eta_seconds 300 \
    updated_at 1700000000
```

### 5.3 Fuzzy Cache Value (JSON)

```json
{
  "query": "madapur",
  "context": {"pincode": "500081", "district": "hyderabad", "state": "telangana"},
  "results": [
    {"canonical_name": "Madhapur", "pincode": "500081", "city": "Hyderabad", "district": "Hyderabad", "state": "Telangana", "score": 92, "method": "fuzzy", "source": "india_post"},
    {"canonical_name": "Madhapur Village", "pincode": "500081", "city": "Hyderabad", "district": "Hyderabad", "state": "Telangana", "score": 78, "method": "fuzzy", "source": "census"}
  ],
  "cached_at": 1700000000
}
```

---

## 6. Indexing Strategy

### 6.1 Primary Database Indexes

| Table | Index | Type | Purpose |
|-------|-------|------|---------|
| `users` | `idx_users_email` | B-tree | Login lookup |
| `users` | `idx_users_status` | Partial B-tree | Active user queries |
| `processing_jobs` | `idx_jobs_user_status` | Composite B-tree | User job history |
| `processing_jobs` | `idx_jobs_created_at` | B-tree DESC | Dashboard recent jobs |
| `processing_jobs` | `idx_jobs_status` | Partial B-tree | Active job monitoring |
| `job_chunks` | `idx_chunks_job_status` | Composite B-tree | Job progress tracking |
| `patient_records` | `idx_patient_records_job_id` | Partition-local B-tree | Job-scoped queries |
| `patient_records` | `idx_patient_records_review_status` | Partial B-tree | Review queue |
| `patient_records` | `idx_patient_records_confidence_tier` | B-tree | Quality filtering |
| `patient_records` | `idx_patient_records_geometry` | GiST | Spatial queries |
| `patient_records` | `idx_patient_records_patient_hash` | B-tree | Deduplication |
| `audit_entries` | `idx_audit_record_id` | B-tree | Record history |
| `audit_entries` | `idx_audit_job_id` | B-tree | Job audit trail |
| `pincode_directory` | `idx_pincode_district_state` | Composite B-tree | Reverse PIN lookup |
| `locality_dictionary` | `idx_locality_canonical` | B-tree | Exact name match |
| `locality_dictionary` | `idx_locality_aliases_gin` | GIN | Alias array search |
| `locality_dictionary` | `idx_locality_pincode` | B-tree | PIN→locality |
| `locality_dictionary` | `idx_locality_city_district` | Composite B-tree | Context filter |
| `locality_dictionary` | `idx_locality_canonical_trgm` | GIN (trgm) | Fallback fuzzy |

### 6.2 Index Maintenance

```sql
-- Automated index maintenance (pg_cron or external scheduler)
-- Run weekly during low traffic

-- Reindex fragmented indexes
REINDEX (CONCURRENTLY) INDEX idx_locality_canonical;
REINDEX (CONCURRENTLY) INDEX idx_patient_records_geometry;

-- Update statistics for query planner
ANALYZE patient_records;
ANALYZE locality_dictionary;
ANALYZE pincode_directory;
```

---

## 7. Partitioning Strategy

### 7.1 Patient Records (Hash Partitioning)

```sql
-- 16 partitions by job_id hash
-- Each partition holds records for ~concurrent_jobs/16 jobs
-- Benefits:
--   - Parallel scan across partitions
--   - Efficient job cleanup (DROP PARTITION)
--   - Even distribution regardless of job size
--   - Local indexes per partition

-- Partition management
-- Drop old job data (cascade to partitions):
ALTER TABLE patient_records DETACH PARTITION patient_records_p3;
DROP TABLE patient_records_p3;
```

### 7.2 Audit Entries (Range Partitioning by Date)

```sql
-- Monthly partitions for audit trail
CREATE TABLE audit_entries (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    record_id UUID NOT NULL,
    job_id UUID NOT NULL,
    field_name VARCHAR(100) NOT NULL,
    old_value TEXT,
    new_value TEXT,
    processing_method processing_method NOT NULL,
    confidence INT NOT NULL CHECK (confidence BETWEEN 0 AND 100),
    source_dataset data_source NOT NULL,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (created_at, id)
) PARTITION BY RANGE (created_at);

-- Create monthly partitions (example for 2025)
CREATE TABLE audit_entries_2025_01 PARTITION OF audit_entries
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
-- ... create through 2025-12

-- Auto-create next month partition (pg_partman or cron job)
```

### 7.3 Job Chunks (List Partitioning by Status)

```sql
-- Not partitioned - small table, frequent status updates
-- Use partial indexes instead
```

---

## 8. Alembic Migration Structure

### 8.1 Migration Directory Layout

```
backend/
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   ├── versions/
│   │   ├── 001_initial_schema.py
│   │   ├── 002_geography_tables.py
│   │   ├── 003_partition_patient_records.py
│   │   ├── 004_audit_partitions.py
│   │   ├── 005_osm_tables.py
│   │   ├── 006_indexes_optimization.py
│   │   └── 007_dataset_versions.py
│   └── README.md
```

### 8.2 Sample Migration (001_initial_schema.py)

```python
"""Initial schema - users, jobs, chunks, patient_records, audit

Revision ID: 001
Revises: 
Create Date: 2025-07-17 10:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Enums
    op.execute("CREATE TYPE user_role AS ENUM ('admin', 'analyst', 'viewer')")
    op.execute("CREATE TYPE user_status AS ENUM ('active', 'inactive', 'locked')")
    op.execute("CREATE TYPE job_status AS ENUM ('pending', 'profiling', 'mapping', 'queued', 'processing', 'completed', 'failed', 'cancelled')")
    op.execute("CREATE TYPE review_status AS ENUM ('auto', 'needs_review', 'manual_verified', 'rejected')")
    op.execute("CREATE TYPE confidence_tier AS ENUM ('high', 'medium', 'low', 'unverified')")
    op.execute("CREATE TYPE match_method AS ENUM ('exact', 'fuzzy', 'inferred', 'manual')")
    op.execute("CREATE TYPE chunk_status AS ENUM ('pending', 'processing', 'completed', 'failed')")
    op.execute("CREATE TYPE processing_method AS ENUM ('normalization', 'parsing', 'pin_resolution', 'locality_match', 'spell_correction', 'hierarchy_enrichment', 'validation_correction', 'manual_override')")
    op.execute("CREATE TYPE data_source AS ENUM ('india_post', 'osm', 'census', 'libpostal', 'rapidfuzz', 'manual', 'inferred')")
    op.execute("CREATE TYPE office_type AS ENUM ('head', 'sub', 'branch')")
    op.execute("CREATE TYPE delivery_status AS ENUM ('delivery', 'non_delivery')")
    op.execute("CREATE TYPE locality_source AS ENUM ('india_post', 'osm', 'census', 'merged')")
    
    # Users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('full_name', sa.String(255), nullable=False),
        sa.Column('role', sa.Enum('admin', 'analyst', 'viewer', name='user_role'), nullable=False, server_default='viewer'),
        sa.Column('status', sa.Enum('active', 'inactive', 'locked', name='user_status'), nullable=False, server_default='active'),
        sa.Column('salt', sa.String(32), nullable=False),
        sa.Column('last_login_at', sa.DateTime(timezone=True)),
        sa.Column('failed_login_attempts', sa.Integer(), default=0),
        sa.Column('locked_until', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_index('idx_users_email', 'users', ['email'])
    op.create_index('idx_users_status', 'users', ['status'], postgresql_where=sa.text("status = 'active'"))
    
    # Processing jobs
    op.create_table(
        'processing_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('filename', sa.String(500), nullable=False),
        sa.Column('original_file_path', sa.String(1000)),
        sa.Column('parquet_file_path', sa.String(1000)),
        sa.Column('total_rows', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_columns', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('column_mapping', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('detected_address_columns', postgresql.ARRAY(sa.Text()), nullable=False, server_default='{}'),
        sa.Column('status', sa.Enum('pending', 'profiling', 'mapping', 'queued', 'processing', 'completed', 'failed', 'cancelled', name='job_status'), nullable=False, server_default='pending'),
        sa.Column('progress_pct', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('processed_rows', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('succeeded_rows', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_rows', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('manual_review_rows', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('chunk_size', sa.Integer(), nullable=False, server_default='50000'),
        sa.Column('total_chunks', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('completed_chunks', postgresql.ARRAY(sa.Integer()), nullable=False, server_default='{}'),
        sa.Column('failed_chunks', postgresql.ARRAY(sa.Integer()), nullable=False, server_default='{}'),
        sa.Column('error_message', sa.Text()),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_index('idx_jobs_user_status', 'processing_jobs', ['user_id', 'status'])
    op.create_index('idx_jobs_created_at', 'processing_jobs', ['created_at'], postgresql_using='btree', postgresql_ops={'created_at': 'DESC'})
    op.create_index('idx_jobs_status', 'processing_jobs', ['status'], postgresql_where=sa.text("status IN ('processing', 'queued')"))
    
    # Job chunks
    op.create_table(
        'job_chunks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('job_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('processing_jobs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('storage_path', sa.String(1000), nullable=False),
        sa.Column('row_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.Enum('pending', 'processing', 'completed', 'failed', name='chunk_status'), nullable=False, server_default='pending'),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_retries', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('error_message', sa.Text()),
        sa.Column('worker_id', sa.String(100)),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.UniqueConstraint('job_id', 'chunk_index', name='uq_job_chunk_index'),
    )
    op.create_index('idx_chunks_job_status', 'job_chunks', ['job_id', 'status'])
    op.create_index('idx_chunks_worker', 'job_chunks', ['worker_id'], postgresql_where=sa.text("status = 'processing'"))
    
    # Job quality stats
    op.create_table(
        'job_quality_stats',
        sa.Column('job_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('processing_jobs.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('total_records', sa.Integer()),
        sa.Column('complete_addresses_before', sa.Integer()),
        sa.Column('missing_pincode_before', sa.Integer()),
        sa.Column('missing_locality_before', sa.Integer()),
        sa.Column('missing_city_before', sa.Integer()),
        sa.Column('missing_district_before', sa.Integer()),
        sa.Column('missing_state_before', sa.Integer()),
        sa.Column('invalid_addresses_before', sa.Integer()),
        sa.Column('duplicate_addresses_before', sa.Integer()),
        sa.Column('overall_quality_before', sa.Float()),
        sa.Column('pincodes_added', sa.Integer()),
        sa.Column('cities_added', sa.Integer()),
        sa.Column('districts_added', sa.Integer()),
        sa.Column('states_added', sa.Integer()),
        sa.Column('spell_corrections', sa.Integer()),
        sa.Column('improved_records', sa.Integer()),
        sa.Column('manual_review_records', sa.Integer()),
        sa.Column('final_quality_score', sa.Float()),
        sa.Column('improvement_percentage', sa.Float()),
        sa.Column('confidence_high', sa.Integer(), default=0),
        sa.Column('confidence_medium', sa.Integer(), default=0),
        sa.Column('confidence_low', sa.Integer(), default=0),
        sa.Column('confidence_unverified', sa.Integer(), default=0),
        sa.Column('profiling_time', sa.Float()),
        sa.Column('processing_time', sa.Float()),
        sa.Column('reporting_time', sa.Float()),
        sa.Column('export_time', sa.Float()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )
    
    # Patient records (partitioned table created in separate migration)
    # Audit entries
    op.create_table(
        'audit_entries',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('record_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('job_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('field_name', sa.String(100), nullable=False),
        sa.Column('old_value', sa.Text()),
        sa.Column('new_value', sa.Text()),
        sa.Column('processing_method', sa.Enum('normalization', 'parsing', 'pin_resolution', 'locality_match', 'spell_correction', 'hierarchy_enrichment', 'validation_correction', 'manual_override', name='processing_method'), nullable=False),
        sa.Column('confidence', sa.Integer(), nullable=False),
        sa.Column('source_dataset', sa.Enum('india_post', 'osm', 'census', 'libpostal', 'rapidfuzz', 'manual', 'inferred', name='data_source'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.CheckConstraint('confidence BETWEEN 0 AND 100', name='ck_audit_confidence'),
    )
    op.create_index('idx_audit_record_id', 'audit_entries', ['record_id'])
    op.create_index('idx_audit_job_id', 'audit_entries', ['job_id'])
    op.create_index('idx_audit_field', 'audit_entries', ['field_name'])
    op.create_index('idx_audit_created_at', 'audit_entries', ['created_at'], postgresql_using='btree', postgresql_ops={'created_at': 'DESC'})

def downgrade():
    op.drop_table('audit_entries')
    op.drop_table('job_quality_stats')
    op.drop_table('job_chunks')
    op.drop_table('processing_jobs')
    op.drop_table('users')
    
    op.execute("DROP TYPE IF EXISTS data_source")
    op.execute("DROP TYPE IF EXISTS processing_method")
    op.execute("DROP TYPE IF EXISTS chunk_status")
    op.execute("DROP TYPE IF EXISTS match_method")
    op.execute("DROP TYPE IF EXISTS confidence_tier")
    op.execute("DROP TYPE IF EXISTS review_status")
    op.execute("DROP TYPE IF EXISTS job_status")
    op.execute("DROP TYPE IF EXISTS user_status")
    op.execute("DROP TYPE IF EXISTS user_role")
```

---

## 9. Reference Data Loading Scripts

### 9.1 India Post PIN Code Loader

```python
# scripts/load_pincode.py
import polars as pl
import asyncio
import asyncpg
from pathlib import Path

async def load_pincode_directory(csv_path: Path, version: str):
    """Load India Post PIN code CSV into PostgreSQL."""
    
    # Read with Polars for speed
    df = pl.read_csv(
        csv_path,
        columns=[
            'pincode', 'office_name', 'office_type', 'delivery_status',
            'district', 'state', 'taluk', 'circle', 'region', 'division',
            'latitude', 'longitude', 'localities'
        ],
        dtypes={
            'pincode': pl.Utf8,
            'office_name': pl.Utf8,
            'office_type': pl.Utf8,
            'delivery_status': pl.Utf8,
            'district': pl.Utf8,
            'state': pl.Utf8,
            'taluk': pl.Utf8,
            'circle': pl.Utf8,
            'region': pl.Utf8,
            'division': pl.Utf8,
            'latitude': pl.Float64,
            'longitude': pl.Float64,
            'localities': pl.Utf8
        }
    )
    
    # Transform
    df = df.with_columns([
        pl.col('pincode').str.strip_chars(),
        pl.col('office_name').str.strip_chars(),
        pl.col('office_type').str.to_lowercase(),
        pl.col('delivery_status').str.to_lowercase(),
        pl.col('district').str.strip_chars().str.title(),
        pl.col('state').str.strip_chars().str.title(),
        pl.col('localities').str.split(',').list.eval(pl.element().str.strip_chars().str.title())
    ])
    
    # Validate PIN codes
    df = df.filter(pl.col('pincode').str.matches(r'^[1-8]\d{5}$'))
    
    conn = await asyncpg.connect(DATABASE_URL)
    
    # Start transaction
    async with conn.transaction():
        # Record dataset version
        await conn.execute("""
            INSERT INTO geography_dataset_versions (dataset_name, version, row_count, checksum_sha256, status)
            VALUES ($1, $2, $3, $4, 'loading')
        """, 'pincode', version, len(df), calculate_sha256(csv_path))
        
        # Truncate and load
        await conn.execute("TRUNCATE pincode_directory")
        
        # Batch insert using COPY for performance
        await conn.copy_records_to_table(
            'pincode_directory',
            records=df.iter_rows(named=True),
            columns=[
                'pincode', 'office_name', 'office_type', 'delivery_status',
                'district', 'state', 'taluk', 'circle', 'region', 'division',
                'latitude', 'longitude', 'localities', 'source_version'
            ]
        )
        
        # Update version status
        await conn.execute("""
            UPDATE geography_dataset_versions 
            SET status = 'loaded', loaded_at = NOW()
            WHERE dataset_name = 'pincode' AND version = $1
        """, version)
    
    await conn.close()
    print(f"Loaded {len(df)} PIN codes")
```

### 9.2 Locality Dictionary Builder

```python
# scripts/build_locality_dictionary.py
import polars as pl
from pathlib import Path

def build_locality_dictionary(
    pincode_csv: Path,
    osm_localities_parquet: Path,
    census_villages_csv: Path,
    output_parquet: Path
) -> pl.DataFrame:
    """Merge India Post, OSM, and Census into unified locality dictionary."""
    
    # 1. India Post localities (from PIN code directory)
    pin_df = pl.read_csv(pincode_csv, columns=['pincode', 'office_name', 'district', 'state', 'localities', 'latitude', 'longitude'])
    pin_localities = pin_df.explode('localities').rename({'localities': 'canonical_name'})
    pin_localities = pin_localities.with_columns([
        pl.lit('india_post').alias('source'),
        pl.col('canonical_name').str.strip_chars().str.title(),
        pl.lit([]).alias('aliases')  # Will populate from OSM
    ])
    
    # 2. OSM localities (place=* tags)
    osm_df = pl.read_parquet(osm_localities_parquet)
    osm_localities = osm_df.select([
        'name', 'pincode', 'city', 'district', 'state', 'latitude', 'longitude',
        pl.lit('osm').alias('source')
    ]).rename({'name': 'canonical_name'})
    osm_localities = osm_localities.with_columns([
        pl.col('canonical_name').str.strip_chars().str.title()
    ])
    
    # 3. Census villages/towns
    census_df = pl.read_csv(census_villages_csv)
    census_localities = census_df.select([
        'village_name', 'pincode', 'district_name', 'state_name', 'latitude', 'longitude',
        pl.lit('census').alias('source'),
        pl.col('level').alias('place_type')
    ]).rename({
        'village_name': 'canonical_name',
        'district_name': 'district',
        'state_name': 'state'
    })
    census_localities = census_localities.with_columns([
        pl.col('canonical_name').str.strip_chars().str.title()
    ])
    
    # 4. Union and deduplicate
    all_localities = pl.concat([pin_localities, osm_localities, census_localities], how='vertical')
    
    # Group by canonical_name + pincode + district + state
    merged = all_localities.group_by([
        'canonical_name', 'pincode', 'city', 'district', 'state'
    ]).agg([
        pl.col('source').first().alias('source'),
        pl.col('latitude').median().alias('latitude'),
        pl.col('longitude').median().alias('longitude'),
        pl.col('place_type').first().alias('place_type'),
        pl.col('canonical_name').alias('aliases')  # Collect all variants
    ])
    
    # Post-process aliases
    merged = merged.with_columns([
        pl.col('aliases').list.unique().alias('aliases')
    ])
    
    # Add ID
    merged = merged.with_row_index('id', offset=1)
    
    # Write output
    merged.write_parquet(output_parquet)
    
    return merged
```

### 9.3 OSM Import (osm2pgsql)

```bash
#!/bin/bash
# scripts/import_osm.sh

OSM_PBF="india-latest.osm.pbf"
FLAT_NODES="/data/flat-nodes.bin"

# Import with slim mode for updates
osm2pgsql \
    --create \
    --slim \
    --flat-nodes "${FLAT_NODES}" \
    --database "postgresql://postgres:password@osm-db:5432/osm" \
    --number-processes 8 \
    --hstore \
    --tag-transform-script style.lua \
    --output-pgsql-flex \
    "${OSM_PBF}"

# Refresh materialized views
psql -h osm-db -d osm -c "SELECT osm.refresh_choropleth_views();"

# Style.lua for admin boundaries only
cat > style.lua << 'EOF'
function osm2pgsql.process_node(object)
    if object.tags.place then
        return {name = object.tags.name, place = object.tags.place}
    end
end

function osm2pgsql.process_way(object)
    if object.tags.boundary == 'administrative' and object.tags.admin_level then
        return {
            admin_level = tonumber(object.tags.admin_level),
            name = object.tags.name,
            name_en = object.tags['name:en'],
            name_hi = object.tags['name:hi']
        }
    end
end

function osm2pgsql.process_relation(object)
    if object.tags.boundary == 'administrative' and object.tags.admin_level then
        return {
            admin_level = tonumber(object.tags.admin_level),
            name = object.tags.name,
            name_en = object.tags['name:en'],
            name_hi = object.tags['name:hi']
        }
    end
end
EOF
```

---

## 10. Data Dictionary

### 10.1 Core Tables

| Table | Column | Type | Constraints | Description |
|-------|--------|------|-------------|-------------|
| `users` | `id` | UUID | PK | Unique user identifier |
| `users` | `email` | VARCHAR(255) | NOT NULL, UNIQUE | Login email |
| `users` | `password_hash` | VARCHAR(255) | NOT NULL | bcrypt hash |
| `users` | `full_name` | VARCHAR(255) | NOT NULL | Display name |
| `users` | `role` | user_role | NOT NULL, DEFAULT 'viewer' | RBAC role |
| `users` | `status` | user_status | NOT NULL, DEFAULT 'active' | Account status |
| `users` | `salt` | VARCHAR(32) | NOT NULL | For patient_id hashing |
| `processing_jobs` | `id` | UUID | PK | Job identifier |
| `processing_jobs` | `user_id` | UUID | FK → users.id | Owner |
| `processing_jobs` | `filename` | VARCHAR(500) | NOT NULL | Original filename |
| `processing_jobs` | `total_rows` | INT | NOT NULL | Row count |
| `processing_jobs` | `column_mapping` | JSONB | NOT NULL | User-confirmed mapping |
| `processing_jobs` | `status` | job_status | NOT NULL | Current state |
| `processing_jobs` | `progress_pct` | REAL | NOT NULL | 0-100 progress |
| `job_chunks` | `id` | UUID | PK | Chunk identifier |
| `job_chunks` | `job_id` | UUID | FK → processing_jobs.id | Parent job |
| `job_chunks` | `chunk_index` | INT | NOT NULL | Sequence number |
| `job_chunks` | `storage_path` | VARCHAR(1000) | NOT NULL | Parquet file location |
| `job_chunks` | `status` | chunk_status | NOT NULL | Processing state |
| `patient_records` | `id` | UUID | PK (composite) | Record identifier |
| `patient_records` | `job_id` | UUID | PK, FK | Partition key |
| `patient_records` | `row_index` | INT | NOT NULL | Original row number |
| `patient_records` | `patient_id_hash` | VARCHAR(64) | NOT NULL | SHA256 hash |
| `patient_records` | `original_address` | JSONB | NOT NULL | Raw input |
| `patient_records` | `normalized_address` | JSONB | NOT NULL | Cleaned |
| `patient_records` | `parsed_address` | JSONB | NOT NULL | libpostal output |
| `patient_records` | `enriched_address` | JSONB | NOT NULL | Final canonical |
| `patient_records` | `confidence_score` | JSONB | NOT NULL | Scoring breakdown |
| `patient_records` | `confidence_tier` | confidence_tier | NOT NULL | HIGH/MEDIUM/LOW/UNVERIFIED |
| `patient_records` | `review_status` | review_status | NOT NULL | Review workflow |
| `patient_records` | `geometry` | GEOGRAPHY(POINT) | | Spatial point |
| `audit_entries` | `id` | UUID | PK | Audit entry ID |
| `audit_entries` | `record_id` | UUID | NOT NULL | FK to patient_records |
| `audit_entries` | `job_id` | UUID | NOT NULL | FK to processing_jobs |
| `audit_entries` | `field_name` | VARCHAR(100) | NOT NULL | Changed field |
| `audit_entries` | `old_value` | TEXT | | Before value |
| `audit_entries` | `new_value` | TEXT | | After value |
| `audit_entries` | `processing_method` | processing_method | NOT NULL | Operation type |
| `audit_entries` | `confidence` | INT | NOT NULL, 0-100 | Match confidence |
| `audit_entries` | `source_dataset` | data_source | NOT NULL | Data source |

### 10.2 Geography Tables

| Table | Column | Type | Constraints | Description |
|-------|--------|------|-------------|-------------|
| `pincode_directory` | `pincode` | CHAR(6) | PK | 6-digit PIN |
| `pincode_directory` | `office_name` | VARCHAR(255) | NOT NULL | Post office name |
| `pincode_directory` | `office_type` | office_type | NOT NULL | Head/Sub/Branch |
| `pincode_directory` | `delivery_status` | delivery_status | NOT NULL | Delivery/Non-delivery |
| `pincode_directory` | `district` | VARCHAR(100) | NOT NULL | District name |
| `pincode_directory` | `state` | VARCHAR(100) | NOT NULL | State name |
| `pincode_directory` | `localities` | TEXT[] | | Served localities |
| `locality_dictionary` | `id` | BIGSERIAL | PK | Unique ID |
| `locality_dictionary` | `canonical_name` | VARCHAR(255) | NOT NULL | Standardized name |
| `locality_dictionary` | `aliases` | TEXT[] | | Alternative names |
| `locality_dictionary` | `pincode` | CHAR(6) | FK | PIN code |
| `locality_dictionary` | `city` | VARCHAR(100) | NOT NULL | City name |
| `locality_dictionary` | `district` | VARCHAR(100) | NOT NULL | District name |
| `locality_dictionary` | `state` | VARCHAR(100) | NOT NULL | State name |
| `locality_dictionary` | `source` | locality_source | NOT NULL | Data origin |
| `census_hierarchy` | `state_code` | CHAR(2) | PK | Census state code |
| `census_hierarchy` | `state_name` | VARCHAR(100) | NOT NULL | State name |
| `census_hierarchy` | `district_code` | CHAR(4) | | District code |
| `census_hierarchy` | `district_name` | VARCHAR(100) | | District name |
| `census_hierarchy` | `village_name` | VARCHAR(255) | | Village/town name |
| `census_hierarchy` | `level` | VARCHAR(20) | NOT NULL | Hierarchy level |
| `geography_dataset_versions` | `dataset_name` | VARCHAR(50) | | Dataset identifier |
| `geography_dataset_versions` | `version` | VARCHAR(50) | | Version string |
| `geography_dataset_versions` | `checksum_sha256` | VARCHAR(64) | | File integrity |
| `geography_dataset_versions` | `status` | VARCHAR(20) | | loading/loaded/failed |

### 10.3 JSONB Structures

#### `original_address` / `normalized_address` / `enriched_address`
```json
{
  "line1": "Flat 404, MG Road",
  "line2": "Koramangala 4th Block",
  "landmark": "Near Forum Mall",
  "locality": "Koramangala",
  "sublocality": "4th Block",
  "city": "Bangalore",
  "district": "Bangalore Urban",
  "state": "Karnataka",
  "pincode": "560034",
  "country": "India",
  "formatted": "Flat 404, MG Road, Koramangala 4th Block, Bangalore 560034, Karnataka, India"
}
```

#### `parsed_address` (libpostal output)
```json
{
  "house_number": "404",
  "street": "MG Road",
  "suburb": "Koramangala",
  "neighbourhood": "4th Block",
  "city": "Bangalore",
  "state_district": "Bangalore Urban",
  "state": "Karnataka",
  "postcode": "560034",
  "country": "India"
}
```

#### `confidence_score`
```json
{
  "overall": 87,
  "pincode_validity": 100,
  "locality_match": 85,
  "hierarchy_consistency": 90,
  "parsing_completeness": 75,
  "fuzzy_quality": 82,
  "method": "fuzzy",
  "tier": "high"
}
```

---

## 11. Maintenance Operations

### 11.1 Routine Maintenance

| Operation | Frequency | Command |
|-----------|-----------|---------|
| Vacuum/Aanalyze patient_records | Daily (autovacuum) | Automatic |
| Reindex fragmented indexes | Weekly | `REINDEX CONCURRENTLY` |
| Update table statistics | Daily | `ANALYZE` |
| Refresh OSM materialized views | After OSM import | `osm.refresh_choropleth_views()` |
| Archive old audit partitions | Monthly | `DETACH PARTITION` + archive |
| Cleanup completed job chunks | After export | `DELETE FROM job_chunks WHERE status='completed'` |

### 11.2 Backup Strategy

| Data | Method | Frequency | Retention |
|------|--------|-----------|-----------|
| Primary PostgreSQL | pg_dump (custom format) | Daily 02:00 UTC | 30 days |
| Primary PostgreSQL | WAL archiving (S3) | Continuous | Point-in-time recovery |
| OSM PostGIS | pg_dump | Weekly | 4 weeks |
| Redis | RDB + AOF | Every 60s | Not backed up (rebuildable) |
| Geography source files | S3 versioned | On load | Indefinite |

### 11.3 Disaster Recovery

```bash
# Restore primary database from backup
pg_restore -d geocare -j 8 -Fc backup_20250717_020000.dump

# Point-in-time recovery
restore_command = 'aws s3 cp s3://geocare-wal/%f %p'
recovery_target_time = '2025-07-17 14:30:00+00'

# Rebuild geography indexes from source
python scripts/build_all_indexes.py --version latest
```

---

## 12. Performance Benchmarks

### 12.1 Expected Query Performance

| Query | Target (p95) | Index Used |
|-------|--------------|------------|
| Get job by ID | < 10 ms | PK |
| List user jobs (20) | < 50 ms | `idx_jobs_user_status` |
| Get job progress | < 5 ms | Redis hash |
| Fetch patient records (page 50) | < 100 ms | Partition scan + `idx_patient_records_job_id` |
| Review queue (needs_review) | < 200 ms | `idx_patient_records_review_queue` |
| Choropleth aggregation (state) | < 500 ms | `idx_patient_records_geometry` + MV |
| PIN code exact lookup | < 1 ms | PK (in-memory cache) |
| Locality fuzzy match (cached) | < 5 ms | Redis |
| Locality fuzzy match (cold) | < 50 ms | `idx_locality_canonical_trgm` |
| Audit trail for record | < 50 ms | `idx_audit_record_id` |

### 12.2 Storage Estimates (10M Records)

| Table | Rows | Row Size | Total Size | Indexes |
|-------|------|----------|------------|---------|
| `processing_jobs` | 10,000 | ~2 KB | 20 MB | 5 MB |
| `job_chunks` | 200,000 | ~500 B | 100 MB | 20 MB |
| `patient_records` | 10,000,000 | ~3 KB | 30 GB | 15 GB |
| `audit_entries` | 50,000,000 | ~400 B | 20 GB | 10 GB |
| `pincode_directory` | 19,000 | ~1 KB | 20 MB | 5 MB |
| `locality_dictionary` | 1,500,000 | ~500 B | 750 MB | 500 MB |
| `census_hierarchy` | 650,000 | ~300 B | 200 MB | 50 MB |
| OSM boundaries | 4,000 | ~5 KB | 20 MB | 50 MB |
| **Total** | | | **~51 GB** | **~26 GB** |

---

**End of Database Design Document v1.0**