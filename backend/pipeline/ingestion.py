"""Live data ingestion for stations, weather, OSM source features and hotspots."""

import csv
import logging
import os
import sys
from datetime import datetime
from io import StringIO
from typing import Callable

import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

logger = logging.getLogger(__name__)
LATEST_WEATHER = {"wind_speed": None, "temperature": None, "humidity": None}
from agents.data_validation_agent import DataValidationAgent
from agents.traffic_analysis_agent import TrafficAnalysisAgent

validation_agent = DataValidationAgent()
traffic_agent = TrafficAnalysisAgent()


def compute_aqi_from_pm25(pm25: float) -> int:
    breakpoints = [(0, 30, 0, 50), (31, 60, 51, 100), (61, 90, 101, 200),
                   (91, 120, 201, 300), (121, 250, 301, 400), (251, 500, 401, 500)]
    for low, high, aqi_low, aqi_high in breakpoints:
        if low <= pm25 <= high:
            return round((aqi_high - aqi_low) * (pm25 - low) / (high - low) + aqi_low)
    return 500 if pm25 > 500 else 0


def fetch_cpcb_aqi():
    """Fetch PM2.5 measurements from CPCB and calculate their CPCB sub-index."""
    try:
        response = requests.get(
            "https://api.data.gov.in/resource/3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69",
            params={"api-key": os.getenv("CPCB_API_KEY", ""), "format": "json",
                    "filters[state]": os.getenv("CITY_STATE", "Delhi"), "limit": 500},
            headers={"User-Agent": "ClearSkies/1.0"}, timeout=30,
        )
        response.raise_for_status()
        stations = {}
        for record in response.json().get("records", []):
            try:
                lat, lon = float(record["latitude"]), float(record["longitude"])
                value = float(record.get("avg_value"))
            except (KeyError, TypeError, ValueError):
                continue
            if not lat or not lon or (record.get("pollutant_id") or "").lower().replace(".", "") not in {"pm25", "pm2.5"}:
                continue
            name = record.get("station") or record.get("station_name")
            if name:
                stations[name] = {"station_name": name, "lat": lat, "lon": lon, "pm25": value,
                                  "aqi": compute_aqi_from_pm25(value), "timestamp": datetime.utcnow()}
        return list(stations.values())
    except Exception as exc:
        logger.warning("CPCB fetch failed: %s", exc)
        return []


def fetch_openaq_fallback():
    """OpenAQ v3 fallback. It is disabled unless an API key is configured."""
    api_key = os.getenv("OPENAQ_API_KEY")
    if not api_key:
        return []
    try:
        response = requests.get(
            "https://api.openaq.org/v3/latest",
            params={"limit": 100, "parameters_id": 2},
            headers={"X-API-Key": api_key, "User-Agent": "ClearSkies/1.0"}, timeout=20,
        )
        response.raise_for_status()
        records = []
        for item in response.json().get("results", []):
            coords = item.get("coordinates") or {}
            pm25 = next((m.get("value") for m in item.get("sensors", [])
                         if m.get("parameter", {}).get("name") == "pm25"), None)
            try:
                lat, lon, pm25 = float(coords["latitude"]), float(coords["longitude"]), float(pm25)
            except (KeyError, TypeError, ValueError):
                continue
            records.append({"station_name": item.get("location", "OpenAQ station"), "lat": lat, "lon": lon,
                            "pm25": pm25, "aqi": compute_aqi_from_pm25(pm25), "timestamp": datetime.utcnow()})
        return records
    except Exception as exc:
        logger.warning("OpenAQ v3 fetch failed: %s", exc)
        return []


def fetch_weather():
    try:
        response = requests.get(
            os.getenv("OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast"),
            params={"latitude": os.getenv("CITY_LAT", "28.6139"), "longitude": os.getenv("CITY_LON", "77.2090"),
                    "current": "temperature_2m,relative_humidity_2m,wind_speed_10m"}, timeout=15,
        )
        response.raise_for_status()
        current = response.json().get("current", {})
        LATEST_WEATHER.update({"wind_speed": current.get("wind_speed_10m"),
                               "temperature": current.get("temperature_2m"),
                               "humidity": current.get("relative_humidity_2m")})
    except Exception as exc:
        logger.warning("Weather fetch failed; readings will retain null weather fields: %s", exc)


def fetch_firms_data():
    key = os.getenv("NASA_FIRMS_MAP_KEY")
    if not key:
        return []
    try:
        bbox = ",".join([os.getenv("CITY_BBOX_WEST", "76.8"), os.getenv("CITY_BBOX_SOUTH", "28.4"),
                         os.getenv("CITY_BBOX_EAST", "77.4"), os.getenv("CITY_BBOX_NORTH", "28.8")])
        response = requests.get(
            f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/VIIRS_SNPP_NRT/{bbox}/1", timeout=20
        )
        response.raise_for_status()
        return [{"lat": float(row["latitude"]), "lon": float(row["longitude"])}
                for row in csv.DictReader(StringIO(response.text))]
    except Exception as exc:
        logger.warning("FIRMS fetch failed: %s", exc)
        return []


def _station_upsert(conn, record):
    return conn.execute(text("""
        INSERT INTO stations (name, lat, lon, ward_id, source)
        VALUES (:name, :lat, :lon,
                (SELECT id FROM wards WHERE ST_Covers(geometry, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)) LIMIT 1),
                :source)
        ON CONFLICT (name) DO UPDATE SET lat = EXCLUDED.lat, lon = EXCLUDED.lon,
            ward_id = COALESCE(EXCLUDED.ward_id, stations.ward_id), source = EXCLUDED.source
        RETURNING id
    """), {"name": record["station_name"], "lat": record["lat"], "lon": record["lon"],
            "source": record.get("source", "cpcb")}).scalar_one()


def sync_overpass_sources(conn):
    """Refresh OSM industrial, construction and primary-road features at most once a day."""
    recent = conn.execute(text("SELECT max(last_inspected) FROM emission_sources WHERE external_id LIKE 'osm:%'")) .scalar()
    if recent and (datetime.utcnow() - recent.replace(tzinfo=None)).total_seconds() < 86400:
        return 0
    try:
        from pipeline.overpass_pull import fetch_osm_features
        bbox = (float(os.getenv("CITY_BBOX_SOUTH", "28.4")), float(os.getenv("CITY_BBOX_WEST", "76.8")),
                float(os.getenv("CITY_BBOX_NORTH", "28.8")), float(os.getenv("CITY_BBOX_EAST", "77.4")))
        written = 0
        for source_type in ("industrial", "construction", "highway"):
            gdf = fetch_osm_features(bbox, source_type)
            db_type = "traffic" if source_type == "highway" else source_type
            for _, feature in gdf.iterrows():
                external_id = f"osm:{source_type}:{feature.get('osm_id', '')}"
                if external_id.endswith(":"):
                    continue
                conn.execute(text("""
                    INSERT INTO emission_sources (type, name, geometry, permit_status, last_inspected, external_id)
                    VALUES (:type, :name, ST_SetSRID(ST_GeomFromText(:geometry), 4326), 'unregistered', now(), :external_id)
                    ON CONFLICT (external_id) WHERE external_id IS NOT NULL DO UPDATE
                    SET geometry = EXCLUDED.geometry, last_inspected = EXCLUDED.last_inspected
                """), {"type": db_type, "name": feature.get("name") or f"OSM {db_type}",
                       "geometry": feature.geometry.wkt, "external_id": external_id})
                written += 1
        return written
    except Exception as exc:
        logger.warning("OSM feature refresh failed; retaining prior features: %s", exc)
        return 0


def _hotspot_features(conn, ward_id: int, pm25: float, anomaly_count: int) -> dict:
    row = conn.execute(text("""
        SELECT LEAST(1.0, count(*) FILTER (WHERE type = 'traffic') / 20.0) AS traffic_density_idx,
               count(*) FILTER (WHERE type = 'construction') / 10.0 AS construction_permit_density,
               count(*) FILTER (WHERE type = 'industrial')::int AS industrial_stack_count
        FROM emission_sources es
        WHERE ST_Covers((SELECT geometry FROM wards WHERE id = :ward_id), ST_PointOnSurface(es.geometry))
    """), {"ward_id": ward_id}).mappings().one()
    return {"traffic_density_idx": traffic_agent.road_density_index(int((row["traffic_density_idx"] or 0) * 20)),
            "construction_permit_density": float(row["construction_permit_density"] or 0),
            "industrial_stack_count": int(row["industrial_stack_count"] or 0),
            "thermal_anomaly_count": anomaly_count, "dust_landuse_pct": 0.0, "pm25": float(pm25)}


def run_ingestion(attribute_hotspot: Callable[[dict], tuple[str, float]] | None = None):
    """Ingest only observed source data. A failed feed writes nothing, never synthetic rows."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.info("Ingestion skipped: DATABASE_URL is not configured.")
        return {"rows_written": 0, "hotspots": 0, "reason": "database_not_configured"}
    records = fetch_cpcb_aqi() or fetch_openaq_fallback()
    if not records:
        logger.warning("No live AQI records available; database left unchanged.")
        return {"rows_written": 0, "hotspots": 0, "reason": "no_live_records"}
    fetch_weather()
    engine = create_engine(database_url, connect_args={"connect_timeout": 10})
    written = hotspots_written = 0
    with engine.begin() as conn:
        sync_overpass_sources(conn)
        for record in records:
            validation = validation_agent.validate_reading(record)
            if not validation.valid:
                logger.warning("Skipping invalid reading from %s: %s", record.get("station_name"), validation.reason)
                continue
            station_id = _station_upsert(conn, record)
            conn.execute(text("""
                INSERT INTO readings (station_id, timestamp, pm25, pm10, aqi, wind_speed, temperature, humidity)
                VALUES (:station_id, :timestamp, :pm25, :pm10, :aqi, :wind_speed, :temperature, :humidity)
                ON CONFLICT (station_id, timestamp) DO NOTHING
            """), {"station_id": station_id, "timestamp": record["timestamp"], "pm25": record["pm25"],
                   "pm10": record.get("pm10"), "aqi": record["aqi"], **LATEST_WEATHER})
            written += 1
        anomalies = {}
        for fire in fetch_firms_data():
            ward_id = conn.execute(text("SELECT id FROM wards WHERE ST_Covers(geometry, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)) LIMIT 1"), fire).scalar()
            if ward_id:
                anomalies[ward_id] = anomalies.get(ward_id, 0) + 1
        readings = conn.execute(text("""
            SELECT DISTINCT ON (s.ward_id) s.ward_id, s.lat, s.lon, r.pm25, r.aqi
            FROM readings r JOIN stations s ON s.id = r.station_id
            WHERE s.ward_id IS NOT NULL AND r.timestamp >= now() - interval '2 hours' AND r.aqi > 150
            ORDER BY s.ward_id, r.aqi DESC
        """)).mappings().all()
        for reading in readings:
            features = _hotspot_features(conn, reading["ward_id"], reading["pm25"], anomalies.get(reading["ward_id"], 0))
            source, confidence = "unknown", 0.0
            if attribute_hotspot:
                try:
                    source, confidence = attribute_hotspot(features)
                except Exception as exc:
                    logger.info("Attribution unavailable for ward %s: %s", reading["ward_id"], exc)
            hotspot_id = conn.execute(text("""
                INSERT INTO hotspots (ward_id, geometry, attributed_source, confidence_score, detected_at,
                    traffic_density_idx, construction_permit_density, industrial_stack_count,
                    thermal_anomaly_count, dust_landuse_pct, pm25)
                VALUES (:ward_id, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :source, :confidence, now(),
                    :traffic_density_idx, :construction_permit_density, :industrial_stack_count,
                    :thermal_anomaly_count, :dust_landuse_pct, :pm25)
                RETURNING id
            """), {**dict(reading), **features, "source": source, "confidence": confidence}).scalar_one()
            conn.execute(text("""
                INSERT INTO enforcement_queue (hotspot_id, priority_score, status)
                VALUES (:hotspot_id, :priority_score, 'pending')
            """), {"hotspot_id": hotspot_id, "priority_score": round((reading["aqi"] / 500) * confidence, 3)})
            hotspots_written += 1
    logger.info("Ingestion finished: %s readings and %s hotspots written", written, hotspots_written)
    return {"rows_written": written, "hotspots": hotspots_written}


if __name__ == "__main__":
    run_ingestion()
