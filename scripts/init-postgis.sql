-- PostGIS initialization script for GeoCare AI
-- Runs on both primary and OSM PostGIS databases

-- Enable PostGIS extension
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS uuid-ossp;

-- Create osm schema for OSM database
CREATE SCHEMA IF NOT EXISTS osm;

-- Grant permissions
GRANT USAGE ON SCHEMA osm TO PUBLIC;
GRANT ALL ON SCHEMA osm TO postgres;

-- OSM admin boundaries table (populated by osm2pgsql)
CREATE TABLE IF NOT EXISTS osm.admin_boundaries (
    id BIGSERIAL PRIMARY KEY,
    osm_id BIGINT NOT NULL,
    admin_level SMALLINT NOT NULL,  -- 4=state, 6=district, 8=city/town, 10=village
    name TEXT NOT NULL,
    name_en TEXT,
    name_hi TEXT,  -- Devanagari
    tags JSONB,
    geom GEOMETRY(MULTIPOLYGON, 4326) NOT NULL,
    way_area DOUBLE PRECISION,
    loaded_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for admin boundaries
CREATE INDEX IF NOT EXISTS idx_osm_admin_level ON osm.admin_boundaries(admin_level);
CREATE INDEX IF NOT EXISTS idx_osm_name ON osm.admin_boundaries(name);
CREATE INDEX IF NOT EXISTS idx_osm_name_en ON osm.admin_boundaries(name_en);
CREATE INDEX IF NOT EXISTS idx_osm_geom ON osm.admin_boundaries USING GIST(geom);

-- Materialized views for choropleth (state and district boundaries)
CREATE MATERIALIZED VIEW IF NOT EXISTS osm.state_boundaries AS
SELECT osm_id, name, name_en, geom
FROM osm.admin_boundaries
WHERE admin_level = 4;

CREATE MATERIALIZED VIEW IF NOT EXISTS osm.district_boundaries AS
SELECT osm_id, name, name_en, geom
FROM osm.admin_boundaries
WHERE admin_level = 6;

CREATE UNIQUE INDEX IF NOT EXISTS idx_state_boundaries_osm_id ON osm.state_boundaries(osm_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_district_boundaries_osm_id ON osm.district_boundaries(osm_id);
CREATE INDEX IF NOT EXISTS idx_state_boundaries_geom ON osm.state_boundaries USING GIST(geom);
CREATE INDEX IF NOT EXISTS idx_district_boundaries_geom ON osm.district_boundaries USING GIST(geom);

-- Function to refresh choropleth views
CREATE OR REPLACE FUNCTION osm.refresh_choropleth_views()
RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY osm.state_boundaries;
    REFRESH MATERIALIZED VIEW CONCURRENTLY osm.district_boundaries;
END $$;

-- Locality points table (OSM POIs with place=* tags)
CREATE TABLE IF NOT EXISTS osm.locality_points (
    id BIGSERIAL PRIMARY KEY,
    osm_id BIGINT NOT NULL,
    name TEXT NOT NULL,
    name_en TEXT,
    place_type TEXT,  -- 'suburb', 'neighbourhood', 'village', 'town', 'city'
    tags JSONB,
    geom GEOMETRY(POINT, 4326) NOT NULL,
    loaded_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_osm_locality_name ON osm.locality_points(name);
CREATE INDEX IF NOT EXISTS idx_osm_locality_place ON osm.locality_points(place_type);
CREATE INDEX IF NOT EXISTS idx_osm_locality_geom ON osm.locality_points USING GIST(geom);

-- Grant permissions on OSM tables
GRANT SELECT ON ALL TABLES IN SCHEMA osm TO PUBLIC;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA osm TO PUBLIC;