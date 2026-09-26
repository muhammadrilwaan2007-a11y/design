-- =============================================================================
-- SafeRoute AI — Migration 001: Live Snapshot System
-- =============================================================================
-- Run this in: Supabase Dashboard → SQL Editor → New Query → Run
--
-- Creates:
--   - live_data_snapshots       (one row per source per refresh event)
--   - incident_observations     (individual incidents per snapshot)
--   - traffic_observations      (traffic flow points per snapshot)
--   - weather_observations      (weather measurements per snapshot)
--   - route_requests            (S→D requests with snapshot linkage)
--
-- PostGIS geography columns (GEOGRAPHY(POINT, 4326)) are created for
-- incident and traffic observations to enable future spatial queries.
--
-- Idempotent: uses IF NOT EXISTS throughout — safe to re-run.
-- =============================================================================

-- Enable PostGIS extension (already available in all Supabase projects)
CREATE EXTENSION IF NOT EXISTS postgis;


-- =============================================================================
-- live_data_snapshots
-- One row per data source (incidents / traffic / weather) per collection run.
-- This is the master table; all observation tables reference it.
-- =============================================================================
CREATE TABLE IF NOT EXISTS live_data_snapshots (
    snapshot_id     UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    collected_at    TIMESTAMPTZ NOT NULL,
    source          TEXT        NOT NULL CHECK (source IN ('incidents', 'traffic', 'weather')),
    status          TEXT        NOT NULL DEFAULT 'ok'
                                CHECK (status IN ('ok', 'partial', 'failed')),
    record_count    INTEGER     NOT NULL DEFAULT 0,
    coverage_area   TEXT        NOT NULL DEFAULT 'bengaluru_wide',
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for freshness queries (most common: "give me the latest fresh snapshot")
CREATE INDEX IF NOT EXISTS idx_snapshots_source_collected
    ON live_data_snapshots (source, collected_at DESC);

CREATE INDEX IF NOT EXISTS idx_snapshots_status
    ON live_data_snapshots (status);

-- Prevent inserting two successful snapshots for the same source within 1 second
-- (extra guard against concurrency edge cases beyond the application-level lock)
CREATE UNIQUE INDEX IF NOT EXISTS idx_snapshots_source_time_unique
    ON live_data_snapshots (source, collected_at)
    WHERE status != 'failed';


-- =============================================================================
-- incident_observations
-- One row per individual TomTom incident in a snapshot.
-- =============================================================================
CREATE TABLE IF NOT EXISTS incident_observations (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id         UUID        NOT NULL
                                    REFERENCES live_data_snapshots(snapshot_id)
                                    ON DELETE CASCADE,
    external_id         TEXT,           -- TomTom incident ID (if provided)
    incident_type       TEXT        NOT NULL DEFAULT 'Unknown',
    icon_category       INTEGER,        -- TomTom iconCategory (1=Accident, 6=Jam, etc.)
    magnitude_of_delay  INTEGER,        -- 0–4 TomTom scale
    latitude            FLOAT8      NOT NULL,
    longitude           FLOAT8      NOT NULL,
    location            GEOGRAPHY(POINT, 4326)
                                    GENERATED ALWAYS AS (
                                        ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography
                                    ) STORED,
    description         TEXT,
    road_name           TEXT,
    from_location       TEXT,
    to_location         TEXT,
    length_meters       FLOAT8,
    delay_seconds       INTEGER,
    start_time          TEXT,
    end_time            TEXT,
    time_validity       TEXT,
    number_of_reports   INTEGER,
    last_report_time    TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_incidents_snapshot_id
    ON incident_observations (snapshot_id);

CREATE INDEX IF NOT EXISTS idx_incidents_location
    ON incident_observations USING GIST (location);

CREATE INDEX IF NOT EXISTS idx_incidents_icon_category
    ON incident_observations (icon_category);

-- Prevent duplicate external_id within the same snapshot
CREATE UNIQUE INDEX IF NOT EXISTS idx_incidents_snapshot_external_id
    ON incident_observations (snapshot_id, external_id)
    WHERE external_id IS NOT NULL;


-- =============================================================================
-- traffic_observations
-- One row per traffic grid point per snapshot.
-- =============================================================================
CREATE TABLE IF NOT EXISTS traffic_observations (
    id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id             UUID        NOT NULL
                                        REFERENCES live_data_snapshots(snapshot_id)
                                        ON DELETE CASCADE,
    latitude                FLOAT8      NOT NULL,
    longitude               FLOAT8      NOT NULL,
    location                GEOGRAPHY(POINT, 4326)
                                        GENERATED ALWAYS AS (
                                            ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography
                                        ) STORED,
    current_speed           FLOAT8,     -- km/h
    free_flow_speed         FLOAT8,     -- km/h
    current_travel_time     FLOAT8,     -- seconds
    free_flow_travel_time   FLOAT8,     -- seconds
    confidence              FLOAT8,     -- 0.0–1.0
    congestion_ratio        FLOAT8,     -- 0.0–1.0 (1-current/freeflow)
    delay_seconds           FLOAT8,     -- current_travel_time - free_flow_travel_time
    road_closure            BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_traffic_snapshot_id
    ON traffic_observations (snapshot_id);

CREATE INDEX IF NOT EXISTS idx_traffic_location
    ON traffic_observations USING GIST (location);

-- Prevent duplicate point within same snapshot
CREATE UNIQUE INDEX IF NOT EXISTS idx_traffic_snapshot_point
    ON traffic_observations (snapshot_id, latitude, longitude);


-- =============================================================================
-- weather_observations
-- One row per weather reading per snapshot.
-- (Currently one per snapshot — city-centre point for Bengaluru.)
-- =============================================================================
CREATE TABLE IF NOT EXISTS weather_observations (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id         UUID        NOT NULL
                                    REFERENCES live_data_snapshots(snapshot_id)
                                    ON DELETE CASCADE,
    latitude            FLOAT8      NOT NULL,
    longitude           FLOAT8      NOT NULL,
    temperature_c       FLOAT8,
    feels_like_c        FLOAT8,
    humidity_percent    INTEGER,
    pressure_hpa        INTEGER,
    visibility_m        INTEGER,
    wind_speed_ms       FLOAT8,
    wind_gust_ms        FLOAT8,
    wind_direction_deg  INTEGER,
    cloudiness_percent  INTEGER,
    weather_id          INTEGER,    -- OpenWeather condition code
    weather_main        TEXT,
    weather_description TEXT,
    rain_1h_mm          FLOAT8      NOT NULL DEFAULT 0,
    snow_1h_mm          FLOAT8      NOT NULL DEFAULT 0,
    collected_at        TIMESTAMPTZ NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_weather_snapshot_id
    ON weather_observations (snapshot_id);

CREATE INDEX IF NOT EXISTS idx_weather_collected_at
    ON weather_observations (collected_at DESC);


-- =============================================================================
-- route_requests
-- Records every S→D route request with the snapshot IDs that were used.
-- This links user requests to the training dataset for future ML validation.
-- =============================================================================
CREATE TABLE IF NOT EXISTS route_requests (
    request_id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    origin_lat              FLOAT8      NOT NULL,
    origin_lon              FLOAT8      NOT NULL,
    destination_lat         FLOAT8      NOT NULL,
    destination_lon         FLOAT8      NOT NULL,
    requested_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    incident_snapshot_id    UUID        REFERENCES live_data_snapshots(snapshot_id),
    traffic_snapshot_id     UUID        REFERENCES live_data_snapshots(snapshot_id),
    weather_snapshot_id     UUID        REFERENCES live_data_snapshots(snapshot_id),
    status                  TEXT        NOT NULL DEFAULT 'completed'
);

CREATE INDEX IF NOT EXISTS idx_route_requests_requested_at
    ON route_requests (requested_at DESC);

CREATE INDEX IF NOT EXISTS idx_route_requests_incident_snapshot
    ON route_requests (incident_snapshot_id);


-- =============================================================================
-- Helper view: latest valid snapshot per source
-- Useful for freshness queries and debugging.
-- =============================================================================
CREATE OR REPLACE VIEW latest_snapshots AS
SELECT DISTINCT ON (source)
    snapshot_id,
    source,
    collected_at,
    status,
    record_count,
    coverage_area,
    error_message
FROM live_data_snapshots
WHERE status != 'failed'
ORDER BY source, collected_at DESC;


-- =============================================================================
-- Confirmation
-- =============================================================================
SELECT
    'live_data_snapshots'   AS table_name, COUNT(*) AS row_count FROM live_data_snapshots UNION ALL
SELECT 'incident_observations',             COUNT(*)              FROM incident_observations UNION ALL
SELECT 'traffic_observations',              COUNT(*)              FROM traffic_observations  UNION ALL
SELECT 'weather_observations',              COUNT(*)              FROM weather_observations  UNION ALL
SELECT 'route_requests',                    COUNT(*)              FROM route_requests;
