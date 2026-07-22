-- Associate pre-existing stations with wards using their PostGIS locations.
-- Live trend and hotspot queries join readings through stations.ward_id, so
-- stations inserted before ward mapping was added are otherwise invisible to
-- all ward-level API responses.

UPDATE stations AS s
SET ward_id = w.id
FROM wards AS w
WHERE s.ward_id IS NULL
  AND ST_Covers(w.geometry, s.location);
