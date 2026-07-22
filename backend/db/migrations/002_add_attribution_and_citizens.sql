-- 002_add_attribution_and_citizens.sql
-- Additive changes needed by the Attribution and Advisory agents that
-- aren't in the current live schema. Safe to run against your existing
-- Neon database -- uses IF NOT EXISTS everywhere, touches no existing data.

-- ---------- hotspots: raw features consumed by the Attribution Agent ----------
-- Your current hotspots table stores the *result* of attribution
-- (attributed_source, confidence_score) but not the inputs that produced
-- it. Storing them lets you retrain/audit/replay attribution later, and
-- lets citizens/officials see "why" on the map.
ALTER TABLE hotspots ADD COLUMN IF NOT EXISTS traffic_density_idx DOUBLE PRECISION;
ALTER TABLE hotspots ADD COLUMN IF NOT EXISTS construction_permit_density DOUBLE PRECISION;
ALTER TABLE hotspots ADD COLUMN IF NOT EXISTS industrial_stack_count INTEGER;
ALTER TABLE hotspots ADD COLUMN IF NOT EXISTS thermal_anomaly_count INTEGER;
ALTER TABLE hotspots ADD COLUMN IF NOT EXISTS dust_landuse_pct DOUBLE PRECISION;
ALTER TABLE hotspots ADD COLUMN IF NOT EXISTS pm25 DOUBLE PRECISION;
ALTER TABLE hotspots ADD COLUMN IF NOT EXISTS source_label TEXT;

-- ---------- citizens: needed by the Citizen Advisory Agent ----------
-- citizen_advisories logs *sent* advisories, but there's no subscriber/
-- profile table yet to generate personalized ones from.
CREATE TABLE IF NOT EXISTS citizens (
    id              TEXT PRIMARY KEY,          -- user_id
    ward_id         INTEGER NOT NULL REFERENCES wards(id),
    language        TEXT NOT NULL DEFAULT 'en',
    conditions      TEXT[] DEFAULT '{}',        -- e.g. {'asthma'}
    elderly         BOOLEAN NOT NULL DEFAULT false,
    outdoor_worker  BOOLEAN NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS idx_citizens_ward ON citizens (ward_id);
