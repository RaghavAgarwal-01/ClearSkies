"""
repository.py
--------------
Real-DB data access functions for Neon Postgres. Each function returns data
in the exact same shape as the corresponding mock_data.py generator, so
agents/api code doesn't need to change at all when you switch from mock to
real data -- only api/main.py's data source calls need to switch.

All read-only, plain SQL via SQLAlchemy `text()` -- no ORM models needed for
a hackathon timeline, and it keeps queries transparent for debugging.
"""

import pandas as pd
from sqlalchemy import text

from db.database import get_engine


def fetch_hotspot_features(limit: int = 500) -> pd.DataFrame:
    """
    Matches mock_data.generate_hotspot_features() output shape:
    ward, traffic_density_idx, construction_permit_density,
    industrial_stack_count, thermal_anomaly_count, dust_landuse_pct, pm25
    (no source_label -- that's only available for historical labeled data,
    if you have any; otherwise train on a labeled subset separately.)
    """
    query = text("""
        SELECT
            w.name AS ward,
            h.traffic_density_idx,
            h.construction_permit_density,
            h.industrial_stack_count,
            h.thermal_anomaly_count,
            h.dust_landuse_pct,
            h.pm25,
            h.source_label AS source_label
        FROM hotspots h
        JOIN wards w ON w.id = h.ward_id
        ORDER BY h.detected_at DESC
        LIMIT :limit
    """)
    with get_engine().connect() as conn:
        return pd.read_sql(query, conn, params={"limit": limit})


def fetch_hotspot_by_id(hotspot_id: int) -> dict | None:
    """Return the stored, observed feature vector for an active hotspot."""
    query = text("""
        SELECT h.id AS hotspot_id, w.name AS ward, h.traffic_density_idx,
               h.construction_permit_density, h.industrial_stack_count,
               h.thermal_anomaly_count, h.dust_landuse_pct, h.pm25,
               h.attributed_source, h.confidence_score
        FROM hotspots h JOIN wards w ON w.id = h.ward_id
        WHERE h.id = :hotspot_id
    """)
    with get_engine().connect() as conn:
        row = conn.execute(query, {"hotspot_id": hotspot_id}).mappings().first()
        return dict(row) if row else None


def fetch_labeled_hotspot_features(limit: int = 1000) -> pd.DataFrame:
    """Training rows only from human-reviewed labels; never fabricate labels."""
    query = text("""
        SELECT w.name AS ward, h.traffic_density_idx, h.construction_permit_density,
               h.industrial_stack_count, h.thermal_anomaly_count, h.dust_landuse_pct,
               h.pm25, h.source_label
        FROM hotspots h JOIN wards w ON w.id = h.ward_id
        WHERE h.source_label IS NOT NULL
          AND h.traffic_density_idx IS NOT NULL
          AND h.construction_permit_density IS NOT NULL
          AND h.industrial_stack_count IS NOT NULL
          AND h.thermal_anomaly_count IS NOT NULL
          AND h.dust_landuse_pct IS NOT NULL
          AND h.pm25 IS NOT NULL
        ORDER BY h.detected_at DESC LIMIT :limit
    """)
    with get_engine().connect() as conn:
        return pd.read_sql(query, conn, params={"limit": limit})


def fetch_prediction_training_data(days: int = 400) -> pd.DataFrame:
    """Build model features from observed readings and weather, including real AQI lags."""
    query = text("""
        WITH daily AS (
            SELECT w.name AS ward, date_trunc('day', r.timestamp)::date AS date,
                   avg(r.aqi) AS aqi, avg(r.temperature) AS temp_c,
                   avg(r.humidity) AS humidity_pct, avg(r.wind_speed) AS wind_speed_kmh
            FROM readings r
            JOIN stations s ON s.id = r.station_id
            JOIN wards w ON w.id = s.ward_id
            WHERE r.timestamp >= now() - (:days || ' days')::interval
              AND r.aqi IS NOT NULL
            GROUP BY w.name, date_trunc('day', r.timestamp)
        ), features AS (
            SELECT *, lag(aqi, 1) OVER ward_window AS aqi_lag_1,
                      lag(aqi, 7) OVER ward_window AS aqi_lag_7
            FROM daily WINDOW ward_window AS (PARTITION BY ward ORDER BY date)
        )
        SELECT ward, date, extract(dow FROM date)::int AS day_of_week,
               extract(month FROM date)::int AS month, temp_c, humidity_pct,
               wind_speed_kmh, 0.0 AS wind_direction_deg, 0.0 AS traffic_density_idx,
               aqi_lag_1, aqi_lag_7, aqi
        FROM features
        WHERE aqi_lag_1 IS NOT NULL AND aqi_lag_7 IS NOT NULL
          AND temp_c IS NOT NULL AND humidity_pct IS NOT NULL AND wind_speed_kmh IS NOT NULL
        ORDER BY ward, date
    """)
    with get_engine().connect() as conn:
        return pd.read_sql(query, conn, params={"days": days})


def fetch_current_conditions(ward_name: str) -> dict | None:
    """Latest measured weather/AQI conditions for forecasting a ward."""
    query = text("""
        WITH latest AS (
            SELECT r.timestamp, r.temperature AS temp_c, r.humidity AS humidity_pct,
                   r.wind_speed AS wind_speed_kmh
            FROM readings r JOIN stations s ON s.id = r.station_id JOIN wards w ON w.id = s.ward_id
            WHERE w.name = :ward_name ORDER BY r.timestamp DESC LIMIT 1
        ), daily AS (
            SELECT date_trunc('day', r.timestamp)::date AS date, avg(r.aqi) AS aqi
            FROM readings r JOIN stations s ON s.id = r.station_id JOIN wards w ON w.id = s.ward_id
            WHERE w.name = :ward_name AND r.aqi IS NOT NULL
            GROUP BY date_trunc('day', r.timestamp)
        ), lags AS (
            SELECT date, aqi, lag(aqi, 1) OVER (ORDER BY date) AS aqi_lag_1,
                   lag(aqi, 7) OVER (ORDER BY date) AS aqi_lag_7 FROM daily
        )
        SELECT latest.*, lags.aqi_lag_1, lags.aqi_lag_7
        FROM latest CROSS JOIN LATERAL (SELECT * FROM lags ORDER BY date DESC LIMIT 1) lags
    """)
    with get_engine().connect() as conn:
        row = conn.execute(query, {"ward_name": ward_name}).mappings().first()
    if not row or any(row[key] is None for key in ("temp_c", "humidity_pct", "wind_speed_kmh", "aqi_lag_1", "aqi_lag_7")):
        return None
    timestamp = row["timestamp"]
    return {
        "ward": ward_name,
        "day_of_week": timestamp.weekday(), "month": timestamp.month,
        "temp_c": float(row["temp_c"]), "humidity_pct": float(row["humidity_pct"]),
        "wind_speed_kmh": float(row["wind_speed_kmh"]), "wind_direction_deg": 0.0,
        "traffic_density_idx": 0.0, "aqi_lag_1": float(row["aqi_lag_1"]),
        "aqi_lag_7": float(row["aqi_lag_7"]),
    }


def fetch_historical_aqi(city: str = None, days: int = 400) -> pd.DataFrame:
    """
    Matches mock_data.generate_historical_aqi() output shape: ward, date, aqi
    Aggregates readings to a daily average per ward via the station->ward link.
    """
    query = text("""
        SELECT
            w.name AS ward,
            date_trunc('day', r.timestamp)::date AS date,
            avg(r.aqi) AS aqi
        FROM readings r
        JOIN stations s ON s.id = r.station_id
        JOIN wards w ON w.id = s.ward_id
        WHERE r.timestamp >= now() - (:days || ' days')::interval
          AND (:city IS NULL OR w.city = :city)
        GROUP BY w.name, date_trunc('day', r.timestamp)
        ORDER BY w.name, date
    """)
    with get_engine().connect() as conn:
        return pd.read_sql(query, conn, params={"days": days, "city": city})


def fetch_citizen_profile(user_id: str) -> dict | None:
    """Matches mock_data.generate_citizen_profile() output shape."""
    query = text("""
        SELECT c.id AS user_id, w.name AS ward, c.language, c.conditions,
               c.outdoor_worker, c.elderly
        FROM citizens c
        JOIN wards w ON w.id = c.ward_id
        WHERE c.id = :user_id
    """)
    with get_engine().connect() as conn:
        row = conn.execute(query, {"user_id": user_id}).mappings().first()
        return dict(row) if row else None


def fetch_latest_forecast(ward_name: str) -> float | None:
    """Latest predicted AQI for a ward, used to feed the Citizen Advisory Agent."""
    query = text("""
        SELECT f.predicted_aqi
        FROM forecasts f
        JOIN wards w ON w.id = f.ward_id
        WHERE w.name = :ward_name
        ORDER BY f.timestamp_generated DESC
        LIMIT 1
    """)
    with get_engine().connect() as conn:
        row = conn.execute(query, {"ward_name": ward_name}).first()
        return float(row[0]) if row else None


def fetch_active_hotspots(limit: int = 10) -> list[dict]:
    """
    Fetches the latest unresolved hotspots from the database, mimicking the shape of MOCK_HOTSPOTS:
    [{"id": str, "ward": str, "source": str, "confidence": float, "aqi": int}]
    """
    query = text("""
        SELECT
            h.id::text,
            w.name AS ward,
            h.attributed_source AS source,
            h.confidence_score AS confidence,
            COALESCE((
                SELECT r.aqi 
                FROM readings r 
                JOIN stations s ON s.id = r.station_id 
                WHERE s.ward_id = w.id 
                ORDER BY r.timestamp DESC LIMIT 1
            ), 0) AS aqi
        FROM hotspots h
        JOIN wards w ON w.id = h.ward_id
        ORDER BY h.detected_at DESC
        LIMIT :limit
    """)
    with get_engine().connect() as conn:
        rows = conn.execute(query, {"limit": limit}).mappings().all()
        return [dict(r) for r in rows]


def fetch_active_hotspots_for_map(ward_name: str = None, limit: int = 200) -> pd.DataFrame:
    """
    Hotspots with lat/lon extracted from the PostGIS `geometry` column
    (ST_Y = lat, ST_X = lon) plus attribution results, ready for the
    Leaflet map layer (Feature 6).
    """
    query = text("""
        SELECT
            h.id AS hotspot_id,
            w.name AS ward,
            ST_Y(h.geometry) AS lat,
            ST_X(h.geometry) AS lon,
            h.attributed_source,
            h.confidence_score,
            h.detected_at,
            COALESCE((
                SELECT r.aqi 
                FROM readings r 
                JOIN stations s ON s.id = r.station_id 
                WHERE s.ward_id = w.id 
                ORDER BY r.timestamp DESC LIMIT 1
            ), 0) AS aqi
        FROM hotspots h
        JOIN wards w ON w.id = h.ward_id
        WHERE (:ward_name IS NULL OR w.name = :ward_name)
        ORDER BY h.detected_at DESC
        LIMIT :limit
    """)
    with get_engine().connect() as conn:
        return pd.read_sql(query, conn, params={"ward_name": ward_name, "limit": limit})


def fetch_emission_sources() -> pd.DataFrame:
    """Emission sources enriched with ward, hotspot distance and inspection age."""
    query = text("""
        SELECT es.id, COALESCE(es.name, 'Unnamed source') AS name, es.type,
               COALESCE(es.permit_status, 'unregistered') AS permit_status,
               w.name AS ward,
               COALESCE(EXTRACT(day FROM now() - es.last_inspected), 365)::int
                   AS days_since_last_inspection,
               COALESCE((
                   SELECT ST_Distance(es.geometry::geography, h.geometry::geography) / 1000.0
                   FROM hotspots h WHERE h.ward_id = w.id
                   ORDER BY h.detected_at DESC LIMIT 1
               ), 3.0) AS distance_to_nearest_hotspot_km
        FROM emission_sources es
        JOIN wards w ON ST_Covers(w.geometry, ST_PointOnSurface(es.geometry))
    """)
    with get_engine().connect() as conn:
        return pd.read_sql(query, conn)


def fetch_ward_names() -> list[str]:
    with get_engine().connect() as conn:
        return [row[0] for row in conn.execute(text("SELECT name FROM wards ORDER BY name"))]


def fetch_city_names() -> list[str]:
    with get_engine().connect() as conn:
        return [row[0] for row in conn.execute(text("SELECT DISTINCT city FROM wards ORDER BY city"))]


def fetch_ward_options() -> list[dict]:
    query = text("""
        SELECT w.name, ST_Y(ST_Centroid(w.geometry)) AS lat, ST_X(ST_Centroid(w.geometry)) AS lng,
               COALESCE((SELECT avg(r.aqi) FROM readings r JOIN stations s ON s.id = r.station_id
                         WHERE s.ward_id = w.id AND r.timestamp >= now() - interval '24 hours'), 0) AS aqi
        FROM wards w ORDER BY w.name
    """)
    with get_engine().connect() as conn:
        return [dict(row) for row in conn.execute(query).mappings().all()]


def fetch_ward_boundaries(city: str | None = None) -> dict:
    query = text("""
        SELECT jsonb_build_object(
            'type', 'FeatureCollection',
            'features', COALESCE(jsonb_agg(jsonb_build_object(
                'type', 'Feature',
                'geometry', ST_AsGeoJSON(w.geometry)::jsonb,
                'properties', jsonb_build_object('id', w.id, 'name', w.name, 'city', w.city)
            )), '[]'::jsonb)
        )
        FROM wards w WHERE (:city IS NULL OR w.city = :city)
    """)
    with get_engine().connect() as conn:
        return conn.execute(query, {"city": city}).scalar_one()


def insert_hotspot_attribution(hotspot_id: int, predicted_source: str, confidence: float) -> None:
    """Writes the Attribution Agent's output back to the hotspots table."""
    query = text("""
        UPDATE hotspots
        SET attributed_source = :source, confidence_score = :confidence
        WHERE id = :hotspot_id
    """)
    with get_engine().begin() as conn:
        conn.execute(query, {"source": predicted_source, "confidence": confidence, "hotspot_id": hotspot_id})


def insert_intervention(enforcement_queue_id: int, aqi_before: int, aqi_after: int, action_taken: str = "Outcome logged") -> None:
    query = text("""
        INSERT INTO interventions (enforcement_queue_id, action_taken, aqi_before, aqi_after)
        VALUES (:queue_id, :action_taken, :aqi_before, :aqi_after)
    """)
    with get_engine().begin() as conn:
        conn.execute(query, {"queue_id": enforcement_queue_id, "action_taken": action_taken,
                             "aqi_before": aqi_before, "aqi_after": aqi_after})
        conn.execute(text("UPDATE enforcement_queue SET status = 'resolved' WHERE id = :queue_id"),
                     {"queue_id": enforcement_queue_id})


def update_enforcement_status(enforcement_queue_id: int, status: str) -> None:
    if status not in {"pending", "dispatched", "resolved"}:
        raise ValueError("Invalid enforcement status")
    with get_engine().begin() as conn:
        result = conn.execute(text("UPDATE enforcement_queue SET status = :status WHERE id = :queue_id"),
                              {"status": status, "queue_id": enforcement_queue_id})
        if result.rowcount == 0:
            raise ValueError("Enforcement queue entry not found")


def fetch_dashboard_enforcement_queue(limit: int = 100) -> list[dict]:
    query = text("""
        SELECT eq.id::text AS id, w.name AS ward, h.attributed_source AS source,
               eq.priority_score, eq.status,
               COALESCE((SELECT r.aqi FROM readings r JOIN stations s ON s.id = r.station_id
                         WHERE s.ward_id = w.id ORDER BY r.timestamp DESC LIMIT 1), 0)::int AS before_aqi,
               (SELECT i.aqi_after FROM interventions i WHERE i.enforcement_queue_id = eq.id
                ORDER BY i.timestamp DESC LIMIT 1) AS after_aqi
        FROM enforcement_queue eq JOIN hotspots h ON h.id = eq.hotspot_id
        JOIN wards w ON w.id = h.ward_id
        ORDER BY eq.created_at DESC LIMIT :limit
    """)
    with get_engine().connect() as conn:
        return [dict(row) for row in conn.execute(query, {"limit": limit}).mappings().all()]


def fetch_latest_station_readings(city: str = None) -> pd.DataFrame:
    """
    Matches mock_data.generate_station_snapshot() output shape:
    station_id, ward, lat, lon, pm25, aqi. Uses the latest reading per
    station -- feeds Feature 6's IDW interpolation.
    """
    query = text("""
        SELECT DISTINCT ON (s.id)
            s.id AS station_id,
            w.name AS ward,
            s.lat, s.lon,
            r.pm25, r.aqi
        FROM stations s
        JOIN wards w ON w.id = s.ward_id
        JOIN readings r ON r.station_id = s.id
        WHERE (:city IS NULL OR w.city = :city)
        ORDER BY s.id, r.timestamp DESC
    """)
    with get_engine().connect() as conn:
        return pd.read_sql(query, conn, params={"city": city})


def fetch_multi_city_summary(cities: list[str], days: int = 30) -> pd.DataFrame:
    """
    Matches mock_data.generate_multi_city_history() output shape:
    city, date, aqi (daily average). Feeds Feature 10's comparison charts.
    """
    query = text("""
        SELECT
            w.city,
            date_trunc('day', r.timestamp)::date AS date,
            avg(r.aqi) AS aqi
        FROM readings r
        JOIN stations s ON s.id = r.station_id
        JOIN wards w ON w.id = s.ward_id
        WHERE w.city = ANY(:cities)
          AND r.timestamp >= now() - (:days || ' days')::interval
        GROUP BY w.city, date_trunc('day', r.timestamp)
        ORDER BY w.city, date
    """)
    with get_engine().connect() as conn:
        return pd.read_sql(query, conn, params={"cities": cities, "days": days})


def fetch_intervention_summary(cities: list[str], days: int = 30) -> pd.DataFrame:
    """City-level intervention count + avg AQI drop, for Feature 10's
    'which city's enforcement is actually working' comparison."""
    query = text("""
        SELECT
            w.city,
            count(i.id) AS intervention_count,
            avg(i.aqi_before - i.aqi_after) AS avg_aqi_drop
        FROM interventions i
        JOIN enforcement_queue eq ON eq.id = i.enforcement_queue_id
        JOIN hotspots h ON h.id = eq.hotspot_id
        JOIN wards w ON w.id = h.ward_id
        WHERE w.city = ANY(:cities)
          AND i.timestamp >= now() - (:days || ' days')::interval
          AND i.aqi_after IS NOT NULL
        GROUP BY w.city
    """)
    with get_engine().connect() as conn:
        return pd.read_sql(query, conn, params={"cities": cities, "days": days})


def fetch_source_breakdown_by_city(cities: list[str], days: int = 30) -> pd.DataFrame:
    """Matches mock_data.generate_source_breakdown_by_city() output shape."""
    query = text("""
        SELECT w.city, h.attributed_source, count(h.id) AS count
        FROM hotspots h
        JOIN wards w ON w.id = h.ward_id
        WHERE w.city = ANY(:cities)
          AND h.detected_at >= now() - (:days || ' days')::interval
          AND h.attributed_source IS NOT NULL
        GROUP BY w.city, h.attributed_source
    """)
    with get_engine().connect() as conn:
        return pd.read_sql(query, conn, params={"cities": cities, "days": days})


def fetch_recent_readings(station_id: int, hours: int = 48) -> pd.DataFrame:
    """
    Matches mock_data.generate_station_reading_series() output shape:
    station_id, timestamp, pm25, aqi. Feeds Feature 11's spike detector
    (rolling z-score + rate-of-change + absolute threshold checks).
    """
    query = text("""
        SELECT station_id, timestamp, pm25, aqi
        FROM readings
        WHERE station_id = :station_id
          AND timestamp >= now() - (:hours || ' hours')::interval
        ORDER BY timestamp ASC
    """)
    with get_engine().connect() as conn:
        return pd.read_sql(query, conn, params={"station_id": station_id, "hours": hours})


def fetch_all_active_station_ids(city: str = None, ward_name: str = None) -> list[int]:
    """List of station IDs to run the Feature 11 spike check against on
    each ingestion cycle."""
    query = text("""
        SELECT s.id FROM stations s
        JOIN wards w ON w.id = s.ward_id
        WHERE (:city IS NULL OR w.city = :city)
          AND (:ward_name IS NULL OR w.name = :ward_name)
    """)
    with get_engine().connect() as conn:
        rows = conn.execute(query, {"city": city, "ward_name": ward_name}).fetchall()
        return [r[0] for r in rows]


def insert_alert_log(recipient: str, channel: str, message: str, risk_level: str, status: str = "sent") -> None:
    """Logs a dispatched notification, with a 30-minute duplicate cooldown."""
    query = text("""
        INSERT INTO alerts_log (recipient, channel, message, risk_level, status)
        SELECT :recipient, :channel, :message, :risk_level, :status
        WHERE NOT EXISTS (
            SELECT 1
            FROM alerts_log
            WHERE recipient = :recipient
              AND channel = :channel
              AND message = :message
              AND risk_level = :risk_level
              AND status = :status
              AND dispatched_at >= now() - INTERVAL '30 minutes'
        )
    """)
    with get_engine().begin() as conn:
        conn.execute(query, {
            "recipient": recipient, "channel": channel, "message": message,
            "risk_level": risk_level, "status": status,
        })


def fetch_recent_alerts(limit: int = 50) -> pd.DataFrame:
    """Matches mock_data.generate_alert_feed() output shape -- feeds the
    citizen-facing Alerts page (Section 11)."""
    query = text("""
        SELECT recipient, channel, message, risk_level, status, dispatched_at
        FROM (
            SELECT DISTINCT ON (recipient, channel, message, risk_level, status)
                   recipient, channel, message, risk_level, status, dispatched_at
            FROM alerts_log
            ORDER BY recipient, channel, message, risk_level, status, dispatched_at DESC
        ) AS latest_alerts
        ORDER BY dispatched_at DESC
        LIMIT :limit
    """)
    with get_engine().connect() as conn:
        return pd.read_sql(query, conn, params={"limit": limit})


def fetch_enforcement_status_counts(city: str = None) -> pd.DataFrame:
    """Matches mock_data.generate_enforcement_queue_snapshot() output shape
    (id, ward, status, priority_score) -- feeds Feature 12's status breakdown."""
    query = text("""
        SELECT eq.id, w.name AS ward, eq.status, eq.priority_score
        FROM enforcement_queue eq
        JOIN hotspots h ON h.id = eq.hotspot_id
        JOIN wards w ON w.id = h.ward_id
        WHERE (:city IS NULL OR w.city = :city)
    """)
    with get_engine().connect() as conn:
        return pd.read_sql(query, conn, params={"city": city})


def fetch_intervention_roi_timeseries(city: str = None, days: int = 60) -> pd.DataFrame:
    """Matches mock_data.generate_intervention_roi_series() output shape
    (date, ward, action_taken, aqi_before, aqi_after) -- feeds Feature 12's
    ROI-over-time chart."""
    query = text("""
        SELECT
            i.timestamp::date AS date,
            w.name AS ward,
            i.action_taken,
            i.aqi_before,
            i.aqi_after
        FROM interventions i
        JOIN enforcement_queue eq ON eq.id = i.enforcement_queue_id
        JOIN hotspots h ON h.id = eq.hotspot_id
        JOIN wards w ON w.id = h.ward_id
        WHERE (:city IS NULL OR w.city = :city)
          AND i.timestamp >= now() - (:days || ' days')::interval
          AND i.aqi_after IS NOT NULL
        ORDER BY date
    """)
    with get_engine().connect() as conn:
        return pd.read_sql(query, conn, params={"city": city, "days": days})


def insert_advisory(ward_name: str, language: str, message: str, risk_level: str) -> None:
    """Logs a dispatched citizen advisory for the audit trail / Section 9 citizen_advisories table."""
    query = text("""
        INSERT INTO citizen_advisories (ward_id, language, message, risk_level)
        SELECT id, :language, :message, :risk_level FROM wards WHERE name = :ward_name
    """)
    with get_engine().begin() as conn:
        conn.execute(query, {"ward_name": ward_name, "language": language, "message": message, "risk_level": risk_level})
