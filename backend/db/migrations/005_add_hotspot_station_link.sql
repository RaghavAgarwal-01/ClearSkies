-- 005_add_hotspot_station_link.sql
-- Ties each hotspot row to the station that triggered it, and enforces at
-- most one active hotspot row per station via a partial unique index.
-- Without this, ingestion has no conflict target to upsert against, so a
-- station that stays above the AQI threshold across multiple 30-minute
-- cycles accumulates a new row every cycle instead of refreshing one.

ALTER TABLE hotspots ADD COLUMN IF NOT EXISTS station_id INTEGER REFERENCES stations(id);

-- Partial (not full-table) unique index: existing legacy rows inserted
-- before this migration have no station_id (NULL) and are left alone --
-- the partial predicate means any number of NULLs can coexist, only
-- non-null station_id values are constrained to be unique. New hotspots
-- inserted by ingestion.py always populate station_id now, so this
-- constraint is what makes ON CONFLICT (station_id) upserts possible.
CREATE UNIQUE INDEX IF NOT EXISTS hotspots_station_id_unique
    ON hotspots (station_id)
    WHERE station_id IS NOT NULL;
