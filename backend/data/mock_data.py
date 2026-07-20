"""
mock_data.py
------------
Synthetic data generators that stand in for the real free-API feeds
(CPCB CAAQMS, Overpass land-use, OSRM traffic, NASA FIRMS thermal anomalies)
so the agents below can be built, tested, and demoed before the
data-pipeline team wires up live ingestion.

Swap these out for real DB queries / API calls without touching agent logic —
each generator's output schema matches what the real pipeline will produce.
"""

import random
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

random.seed(42)
np.random.seed(42)

WARDS = [
    "Anand Vihar", "ITO", "Dwarka Sec-8", "Rohini", "Connaught Place",
    "Nehru Nagar", "Okhla Phase-II", "Patel Nagar", "Shahdara", "Kidwai Nagar",
]

SOURCE_PROFILES = {
    # ward -> dominant ground-truth source (used only to generate realistic mock data)
    "Anand Vihar": "traffic",
    "ITO": "traffic",
    "Dwarka Sec-8": "dust",
    "Rohini": "construction",
    "Connaught Place": "traffic",
    "Nehru Nagar": "construction",
    "Okhla Phase-II": "industrial",
    "Patel Nagar": "construction",
    "Shahdara": "industrial",
    "Kidwai Nagar": "construction",
}

FESTIVALS_2025_26 = {
    "Diwali": datetime(2025, 10, 21),
    "Holi": datetime(2026, 3, 4),
    "Harvest/Stubble Season Start": datetime(2025, 10, 1),
}

CITIES = ["Lucknow", "Delhi", "Mumbai", "Kanpur"]

WARD_CENTERS = {
    # Rough lat/lon per ward (New Delhi), used only so heatmap interpolation
    # has somewhere realistic to draw points -- swap for real station
    # lat/lon (Section 9's `stations` table) once ingestion is live.
    "Anand Vihar": (28.6469, 77.3164),
    "ITO": (28.6289, 77.2414),
    "Dwarka Sec-8": (28.5733, 77.0651),
    "Rohini": (28.7324, 77.1108),
    "Connaught Place": (28.6315, 77.2167),
    "Nehru Nagar": (28.6507, 77.2723),
    "Okhla Phase-II": (28.5308, 77.2713),
    "Patel Nagar": (28.6512, 77.1639),
    "Shahdara": (28.6736, 77.2905),
    "Kidwai Nagar": (28.5795, 77.2090),
}


def generate_hotspot_features(n_per_ward: int = 30) -> pd.DataFrame:
    """
    Generates hotspot-level feature rows: land-use %, traffic density index,
    satellite thermal anomaly count, construction permit density, industrial
    stack count -- the inputs the Attribution Agent consumes.
    """
    rows = []
    for ward in WARDS:
        dominant = SOURCE_PROFILES[ward]
        for _ in range(n_per_ward):
            base = {
                "ward": ward,
                "traffic_density_idx": np.random.uniform(0.1, 0.4),
                "construction_permit_density": np.random.uniform(0.0, 0.2),
                "industrial_stack_count": np.random.poisson(0.5),
                "thermal_anomaly_count": np.random.poisson(0.2),
                "dust_landuse_pct": np.random.uniform(0.0, 0.15),
                "pm25": np.random.uniform(40, 90),
            }
            # bias features toward the ward's dominant source so the
            # classifier has a real signal to learn during the demo
            if dominant == "traffic":
                base["traffic_density_idx"] += np.random.uniform(0.3, 0.5)
                base["pm25"] += 30
            elif dominant == "construction":
                base["construction_permit_density"] += np.random.uniform(0.3, 0.5)
                base["pm25"] += 25
            elif dominant == "industrial":
                base["industrial_stack_count"] += np.random.poisson(3)
                base["pm25"] += 40
            elif dominant == "dust":
                base["dust_landuse_pct"] += np.random.uniform(0.3, 0.5)
                base["pm25"] += 20
            elif dominant == "stubble_burning":
                base["thermal_anomaly_count"] += np.random.poisson(4)
                base["pm25"] += 50

            base["source_label"] = dominant  # ground truth, used for training only
            rows.append(base)
    return pd.DataFrame(rows)


def generate_citizen_profile(user_id: str) -> dict:
    profiles = [
        {"user_id": user_id, "ward": "Ward-1", "language": "en", "conditions": ["asthma"], "outdoor_worker": False, "elderly": False},
        {"user_id": user_id, "ward": "Ward-3", "language": "hi", "conditions": [], "outdoor_worker": True, "elderly": False},
        {"user_id": user_id, "ward": "Ward-6", "language": "hi", "conditions": [], "outdoor_worker": False, "elderly": True},
    ]
    return random.choice(profiles)


def generate_prediction_training_data(days: int = 400) -> pd.DataFrame:
    """
    Historical rows with weather + traffic + lag features + target AQI,
    for training the LightGBM forecasting model (Feature 1).
    """
    hist = generate_historical_aqi(days=days)
    hist["date"] = pd.to_datetime(hist["date"])
    hist = hist.sort_values(["ward", "date"])

    rows = []
    for ward, group in hist.groupby("ward"):
        group = group.reset_index(drop=True)
        for i in range(7, len(group)):  # need 7 days of lag history
            row = group.iloc[i]
            date = row["date"]
            rows.append({
                "ward": ward,
                "date": date,
                "day_of_week": date.weekday(),
                "month": date.month,
                "temp_c": np.random.uniform(10, 35) - (5 if date.month in (12, 1, 2) else 0),
                "humidity_pct": np.random.uniform(30, 85),
                "wind_speed_kmh": np.random.uniform(2, 25),
                "wind_direction_deg": np.random.uniform(0, 360),
                "traffic_density_idx": np.random.uniform(0.2, 0.9),
                "aqi_lag_1": group.iloc[i - 1]["aqi"],
                "aqi_lag_7": group.iloc[i - 7]["aqi"],
                "aqi": row["aqi"],  # target
            })
    return pd.DataFrame(rows)


def generate_current_conditions(ward: str) -> dict:
    """Current weather/traffic snapshot + recent AQI lags, used as inference input for the Prediction Agent."""
    return {
        "ward": ward,
        "day_of_week": datetime.now().weekday(),
        "month": datetime.now().month,
        "temp_c": np.random.uniform(15, 30),
        "humidity_pct": np.random.uniform(35, 80),
        "wind_speed_kmh": np.random.uniform(3, 20),
        "wind_direction_deg": np.random.uniform(0, 360),
        "traffic_density_idx": np.random.uniform(0.3, 0.8),
        "aqi_lag_1": np.random.uniform(80, 220),
        "aqi_lag_7": np.random.uniform(80, 220),
    }


def generate_emission_sources(n: int = 20) -> pd.DataFrame:
    """
    Registered emission sources with permit + inspection history, used by
    the Enforcement Prioritization Agent (Feature 4).
    """
    types = ["industry", "construction", "waste_burning_site", "diesel_depot"]
    rows = []
    for i in range(n):
        rows.append({
            "id": i + 1,
            "ward": random.choice(WARDS),
            "type": random.choice(types),
            "name": f"Site-{i+1}",
            "permit_status": random.choice(["valid", "expired", "unregistered"]),
            "days_since_last_inspection": random.choice([5, 15, 45, 90, 200, 400]),
            "distance_to_nearest_hotspot_km": round(np.random.uniform(0.1, 3.0), 2),
        })
    return pd.DataFrame(rows)


def generate_realtime_readings(ward: str, spike: bool = True) -> pd.DataFrame:
    """
    Sub-hourly AQI readings over the last few hours for a single ward.
    NOTE: this was the input shape for an earlier ward-keyed version of the
    Emergency Detection Agent (Feature 11). The current emergency_agent.py
    uses generate_station_reading_series() (station-keyed) instead, since
    that matches the actual DB schema (readings.station_id FK). Kept here
    in case other code (e.g. Feature 4's enforcement view) still wants a
    ward-level realtime feed.
    """
    now = datetime.now()
    timestamps = [now - timedelta(minutes=15 * i) for i in range(12)][::-1]  # last 3 hours, 15-min steps
    base = np.random.uniform(90, 130)
    readings = [base + np.random.normal(0, 5) for _ in timestamps]

    if spike:
        # last 3 readings ramp up sharply -- simulates a fast-onset emergency
        readings[-3] += 60
        readings[-2] += 130
        readings[-1] += 220

    return pd.DataFrame({"ward": ward, "timestamp": timestamps, "aqi": [round(r, 1) for r in readings]})


def generate_station_snapshot(n_stations_per_ward: int = 2) -> pd.DataFrame:
    """
    Feature 6 (Geospatial Heatmaps) input: latest station readings with
    lat/lon, matching what `repository.fetch_latest_station_readings()`
    will return once ingestion is live (station_id, lat, lon, ward,
    pm25, aqi).
    """
    rows = []
    station_id = 0
    for ward, (lat, lon) in WARD_CENTERS.items():
        dominant = SOURCE_PROFILES[ward]
        base_aqi = {"traffic": 220, "construction": 180, "industrial": 240,
                    "dust": 160, "stubble_burning": 280}[dominant]
        for i in range(n_stations_per_ward):
            station_id += 1
            jitter_lat = lat + np.random.uniform(-0.01, 0.01)
            jitter_lon = lon + np.random.uniform(-0.01, 0.01)
            aqi = max(20, base_aqi + np.random.normal(0, 25))
            rows.append({
                "station_id": station_id,
                "ward": ward,
                "lat": round(jitter_lat, 5),
                "lon": round(jitter_lon, 5),
                "pm25": round(aqi * 0.6, 1),
                "aqi": round(aqi, 1),
            })
    return pd.DataFrame(rows)


def generate_multi_city_history(days: int = 30) -> pd.DataFrame:
    """
    Feature 10 (Multi-city Comparison) input: daily average AQI per city
    plus a running count of logged interventions and their average AQI
    drop, matching `repository.fetch_multi_city_summary()`'s output shape.
    """
    city_baselines = {"Lucknow": 190, "Delhi": 260, "Mumbai": 140, "Kanpur": 230}
    rows = []
    start = datetime.now() - timedelta(days=days)
    for city in CITIES:
        base = city_baselines.get(city, 180)
        interventions_so_far = 0
        for d in range(days):
            date = start + timedelta(days=d)
            noise = np.random.normal(0, 15)
            # cities with more interventions trend down slightly over the window
            trend = -0.3 * interventions_so_far
            aqi = max(20, base + noise + trend)
            if np.random.random() < 0.15:  # occasional logged intervention
                interventions_so_far += 1
                aqi_drop = np.random.uniform(10, 40)
            else:
                aqi_drop = 0
            rows.append({
                "city": city,
                "date": date.date(),
                "aqi": round(aqi, 1),
                "intervention_logged": aqi_drop > 0,
                "aqi_drop": round(aqi_drop, 1),
            })
    return pd.DataFrame(rows)


def generate_source_breakdown_by_city() -> pd.DataFrame:
    """Feature 10 supporting data: hotspot source-category counts per city,
    matching a `GROUP BY city, attributed_source` query on `hotspots`."""
    rows = []
    for city in CITIES:
        for source, count in zip(
            ["traffic", "construction", "industrial", "dust", "stubble_burning"],
            np.random.poisson(6, size=5),
        ):
            rows.append({"city": city, "attributed_source": source, "count": int(count)})
    return pd.DataFrame(rows)


def generate_station_reading_series(station_id: int = 1, hours: int = 48, spike: bool = True) -> pd.DataFrame:
    """
    Feature 11 (Emergency Pollution Detection) input: an hourly PM2.5 + AQI
    time series for one station. When spike=True (default), a sudden jump
    is injected near the end so both the rolling z-score check and the
    rate-of-change/absolute-threshold checks have something real to catch.
    Matches `repository.fetch_recent_readings(station_id)`'s output shape.
    """
    ts = pd.date_range(end=datetime.now(), periods=hours, freq="h")
    baseline = np.random.normal(60, 8, size=hours)
    baseline = np.clip(baseline, 20, None)
    if spike:
        # inject a spike in the last 2 hours to simulate a fire/industrial incident
        baseline[-2:] += np.random.uniform(120, 200, size=2)
    pm25 = np.round(baseline, 1)
    aqi = np.round(pm25 * 1.8, 1)  # rough PM2.5 -> AQI scaling for mock purposes only
    return pd.DataFrame({
        "station_id": station_id,
        "timestamp": ts,
        "pm25": pm25,
        "aqi": aqi,
    })


def generate_alert_feed(n: int = 15) -> pd.DataFrame:
    """
    Feature 9 (Real-time Alerts) input: a recent dispatch history, matching
    `repository.fetch_recent_alerts()`'s output shape -- feeds the
    citizen-facing Alerts page.
    """
    channels = ["push", "sms", "app_feed"]
    risk_levels = ["moderate", "poor", "very_poor", "severe", "critical"]
    rows = []
    now = datetime.now()
    for i in range(n):
        ward = np.random.choice(WARDS)
        risk = np.random.choice(risk_levels, p=[0.3, 0.3, 0.2, 0.15, 0.05])
        rows.append({
            "recipient": ward,
            "channel": np.random.choice(channels),
            "message": f"Air quality advisory for {ward}: risk level {risk}.",
            "risk_level": risk,
            "status": "sent",
            "dispatched_at": now - timedelta(minutes=int(np.random.uniform(0, 720))),
        })
    return pd.DataFrame(rows).sort_values("dispatched_at", ascending=False).reset_index(drop=True)


def generate_enforcement_queue_snapshot(n: int = 25) -> pd.DataFrame:
    """
    Feature 12 (Analytics Dashboard) input: matches
    `repository.fetch_enforcement_status_counts()`'s output shape
    (id, ward, status, priority_score) so AnalyticsAgent can roll up
    queue status without touching the live enforcement_agent ranking.
    """
    statuses = ["pending", "assigned", "resolved"]
    rows = []
    for i in range(n):
        rows.append({
            "id": i + 1,
            "ward": np.random.choice(WARDS),
            "status": np.random.choice(statuses, p=[0.45, 0.25, 0.30]),
            "priority_score": round(float(np.random.uniform(20, 95)), 1),
        })
    return pd.DataFrame(rows)


def generate_intervention_roi_series(days: int = 30) -> pd.DataFrame:
    """
    Feature 12 (Analytics Dashboard) input: matches
    `repository.fetch_intervention_roi_timeseries()`'s output shape
    (date, ward, action_taken, aqi_before, aqi_after) -- the data that
    powers the "did our interventions actually work" ROI chart, which is
    the closed-feedback-loop story from Section 1 of the plan.
    """
    action_types = [
        "water_sprinkling", "construction_stop_work", "traffic_diversion",
        "industrial_emission_check", "dust_suppression",
    ]
    # Give each action type a distinct, semi-realistic effectiveness so
    # "best_action_type" in the summary isn't just noise.
    action_effect = {
        "water_sprinkling": 35, "construction_stop_work": 55,
        "traffic_diversion": 25, "industrial_emission_check": 40,
        "dust_suppression": 30,
    }
    rows = []
    start = datetime.now() - timedelta(days=days)
    for d in range(days):
        date = (start + timedelta(days=d)).date()
        for _ in range(np.random.randint(0, 3)):  # 0-2 interventions logged that day
            action = np.random.choice(action_types)
            aqi_before = float(np.random.uniform(180, 420))
            drop = action_effect[action] + np.random.normal(0, 12)
            aqi_after = max(20.0, aqi_before - drop)
            rows.append({
                "date": date,
                "ward": np.random.choice(WARDS),
                "action_taken": action,
                "aqi_before": round(aqi_before, 1),
                "aqi_after": round(aqi_after, 1),
            })
    return pd.DataFrame(rows)


def generate_historical_aqi(days: int = 400) -> pd.DataFrame:
    """
    Generates a daily AQI time series per ward with:
      - a mild upward winter seasonal bump
      - weekday/weekend traffic effect
      - festival spikes (Diwali, harvest/stubble season)
    so the Trend Analysis agent has real patterns to detect.
    """
    start = datetime.now() - timedelta(days=days)
    rows = []
    for ward in WARDS:
        base_level = np.random.uniform(90, 140)
        for d in range(days):
            date = start + timedelta(days=d)
            seasonal = 30 * np.sin((date.timetuple().tm_yday / 365) * 2 * np.pi + np.pi)  # peaks in winter
            weekday_effect = -10 if date.weekday() >= 5 else 5  # weekends slightly cleaner
            noise = np.random.normal(0, 8)

            festival_bump = 0
            for name, fdate in FESTIVALS_2025_26.items():
                if 0 <= (date - fdate).days <= 3:
                    festival_bump += 60 if name == "Diwali" else 35

            aqi = max(20, base_level + seasonal + weekday_effect + noise + festival_bump)
            rows.append({"ward": ward, "date": date.date(), "aqi": round(aqi, 1)})
    return pd.DataFrame(rows)