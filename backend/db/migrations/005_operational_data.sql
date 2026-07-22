-- Operational tables/constraints needed by the live pipeline and dashboards.

CREATE TABLE IF NOT EXISTS alerts_log (
    id BIGSERIAL PRIMARY KEY,
    recipient TEXT NOT NULL,
    channel TEXT NOT NULL,
    message TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'sent',
    dispatched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_alerts_log_dispatched_at ON alerts_log (dispatched_at DESC);

-- Makes scheduled ingestion idempotent when upstream feeds repeat a timestamp.
CREATE UNIQUE INDEX IF NOT EXISTS readings_station_timestamp_unique
    ON readings (station_id, timestamp);

-- Do not create duplicate active hotspot records for the same ward/location
-- during repeated ingestion runs. Existing historical rows are left untouched.
CREATE INDEX IF NOT EXISTS idx_hotspots_recent_ward ON hotspots (ward_id, detected_at DESC);

ALTER TABLE emission_sources ADD COLUMN IF NOT EXISTS external_id TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS emission_sources_external_id_unique
    ON emission_sources (external_id) WHERE external_id IS NOT NULL;
