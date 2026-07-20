"""
main.py
-------
FastAPI wiring for System Features 1, 2, 3, 4, 5, 7, and 11 so the frontend
team can hit real endpoints immediately, using mock data until the
ingestion pipeline is connected.

(Note: Trend Analysis is Feature 7 in the plan's Section 2 list, not
Feature 10 as an earlier version of this file said -- fixed here.)

Run: uvicorn api.main:app --reload --port 8000
Docs: http://localhost:8000/docs
"""

import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__)))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from agents.attribution_agent import PollutionAttributionAgent
from agents.advisory_agent import CitizenAdvisoryAgent
from agents.trend_agent import TrendAnalysisAgent
from apscheduler.schedulers.background import BackgroundScheduler
from pipeline.ingestion import run_ingestion
from agents.recommendation_agent import RecommendationAgent
from agents.explanation_agent import ExplanationAgent
from db.database import is_db_configured
from agents.prediction_agent import AQIPredictionAgent
from agents.enforcement_agent import EnforcementPrioritizationAgent
from agents.emergency_agent import EmergencyDetectionAgent
from db.repository import fetch_active_hotspots
from data.mock_data import (
    generate_hotspot_features,
    generate_historical_aqi,
    generate_prediction_training_data,
    generate_current_conditions,
    generate_emission_sources,
    generate_station_snapshot,
    generate_multi_city_history,
    generate_source_breakdown_by_city,
    generate_station_reading_series,
    generate_alert_feed,
    generate_enforcement_queue_snapshot,
    generate_intervention_roi_series,
    FESTIVALS_2025_26,
    CITIES,
)

from agents.heatmap_agent import HeatmapAgent
from agents.comparison_agent import MultiCityComparisonAgent
from agents.chat_agent import ChatAssistantAgent
from agents.analytics_agent import AnalyticsAgent
from agents.alert_agent import RealTimeAlertAgent
from data.knowledge_corpus import DOCS

app = FastAPI(title="AirPulse — Features 2, 5, 10")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

USING_REAL_DB = is_db_configured()

if USING_REAL_DB:
    # Real Neon data. Note: attribution training still needs labeled data --
    # if your hotspots table doesn't have source_label populated yet, keep
    # training on mock data (which has labels) and only swap inference/trend
    # data sources to real DB. Adjust the two lines below once you have
    # labeled hotspot data to train on.
    from db.repository import fetch_hotspot_features, fetch_historical_aqi
    _training_df = generate_hotspot_features()  # swap to a labeled real query once available
    _historical_df = fetch_historical_aqi()
else:
    _training_df = generate_hotspot_features()
    _historical_df = generate_historical_aqi()

# --- Startup: train models once ---
attribution_agent = PollutionAttributionAgent()
_training_report = attribution_agent.train(_training_df)

prediction_agent = AQIPredictionAgent()
_prediction_training_df = generate_prediction_training_data()  # swap to real historical query once you have enough real days
_prediction_metrics = prediction_agent.train(_prediction_training_df)

advisory_agent = CitizenAdvisoryAgent()
trend_agent = TrendAnalysisAgent()
recommendation_agent = RecommendationAgent()
enforcement_agent = EnforcementPrioritizationAgent()
emergency_agent = EmergencyDetectionAgent()

_emission_sources_df = generate_emission_sources()  # swap to a real `emission_sources` table query
heatmap_agent = HeatmapAgent()
comparison_agent = MultiCityComparisonAgent()
chat_agent = ChatAssistantAgent(DOCS)
analytics_agent = AnalyticsAgent()
alert_agent = RealTimeAlertAgent()


# ---------- Hotspots API (Live) ----------

@app.get("/api/hotspots")
def get_hotspots():
    if USING_REAL_DB:
        from db.repository import fetch_active_hotspots_for_map
        import pandas as pd
        df = fetch_active_hotspots_for_map()
        hotspots_list = []
        for _, row in df.iterrows():
            hotspots_list.append({
                "id": str(row["hotspot_id"]),
                "zone": row["ward"],
                "lat": row["lat"],
                "lng": row["lon"],
                "source": row["attributed_source"] if pd.notnull(row["attributed_source"]) else "unknown",
                "confidence": round(row["confidence_score"] * 100) if pd.notnull(row["confidence_score"]) else 0,
                "aqi": int(row["aqi"]) if pd.notnull(row["aqi"]) else 0,
            })
        return hotspots_list
    else:
        # User explicitly requested real-time data, so if the DB is down, return empty
        return []


# ---------- Feature 2: Source Attribution ----------

class HotspotInput(BaseModel):
    ward: str
    traffic_density_idx: float
    construction_permit_density: float
    industrial_stack_count: int
    thermal_anomaly_count: int
    dust_landuse_pct: float
    pm25: float


class HotspotInputWithId(HotspotInput):
    hotspot_id: Optional[int] = None  # pass this to persist the result back to Neon


@app.post("/api/attribution")
def attribute_hotspot(hotspot: HotspotInputWithId):
    import pandas as pd
    row = pd.Series(hotspot.model_dump(exclude={"hotspot_id"}))
    result = attribution_agent.attribute(row)

    if USING_REAL_DB and hotspot.hotspot_id is not None:
        from db.repository import insert_hotspot_attribution
        insert_hotspot_attribution(hotspot.hotspot_id, result.predicted_source, result.confidence)

    return {
        "ward": result.ward,
        "predicted_source": result.predicted_source,
        "confidence": result.confidence,
        "all_probabilities": result.all_probabilities,
        "evidence": result.evidence,
    }


@app.get("/api/attribution/model-report")
def get_model_report():
    return {"classification_report": _training_report}


# ---------- Feature 5: Citizen Health Advisory ----------

class AdvisoryRequest(BaseModel):
    user_id: str
    ward: str
    language: str = "en"
    conditions: Optional[List[str]] = None
    elderly: bool = False
    outdoor_worker: bool = False
    forecast_aqi: float


@app.post("/api/advisory")
def get_advisory(req: AdvisoryRequest):
    from agents.advisory_agent import CitizenProfile
    profile = CitizenProfile(
        user_id=req.user_id,
        ward=req.ward,
        language=req.language,
        conditions=req.conditions or [],
        elderly=req.elderly,
        outdoor_worker=req.outdoor_worker,
    )
    advisory = advisory_agent.generate(profile, req.forecast_aqi)

    if USING_REAL_DB:
        from db.repository import insert_advisory
        insert_advisory(advisory.ward, advisory.language, advisory.message, advisory.risk_level)

    return {
        "user_id": advisory.user_id,
        "ward": advisory.ward,
        "language": advisory.language,
        "risk_level": advisory.risk_level,
        "forecast_aqi": advisory.forecast_aqi,
        "message": advisory.message,
    }


# ---------- Feature 7: Trend Analysis ----------

@app.get("/api/trends/{ward}")
def get_ward_trends(ward: str):
    if ward not in _historical_df["ward"].unique():
        raise HTTPException(status_code=404, detail=f"No data for ward '{ward}'")
    report = trend_agent.analyze_ward(_historical_df, ward, FESTIVALS_2025_26)
    return {
        "ward": report.ward,
        "avg_aqi": report.avg_aqi,
        "weekday_avg": report.weekday_avg,
        "weekend_avg": report.weekend_avg,
        "weekday_vs_weekend_delta": report.weekday_vs_weekend_delta,
        "monthly_avg": report.monthly_avg,
        "peak_month": report.peak_month,
        "festival_spikes": report.festival_spikes,
        "anomaly_days": report.anomaly_days,
    }


@app.get("/api/trends")
def get_all_trends():
    reports = trend_agent.analyze_all_wards(_historical_df, FESTIVALS_2025_26)
    return {
        ward: {
            "avg_aqi": r.avg_aqi,
            "peak_month": r.peak_month,
            "festival_spikes": r.festival_spikes,
            "anomaly_count": len(r.anomaly_days),
        }
        for ward, r in reports.items()
    }


# ---------- Feature: Admin Enforcement Queue ----------

# Maps hotspot "source" labels (used elsewhere in the app / mock data) to the
# keys RecommendationAgent's ACTION_MATRIX actually understands.
_SOURCE_ALIAS = {
    "vehicular": "traffic",
}

@app.get("/api/enforcement-queue")
def get_enforcement_queue():
    agent = RecommendationAgent()

    if USING_REAL_DB:
        hotspots = fetch_active_hotspots(limit=10)
    else:
        hotspots = []

    if not hotspots:
        hotspots = [
            {"id": "enf-001", "ward": "Shahdara", "source": "industrial", "confidence": 0.88, "aqi": 420},
            {"id": "enf-002", "ward": "Anand Vihar", "source": "vehicular", "confidence": 0.92, "aqi": 390},
            {"id": "enf-003", "ward": "Nehru Nagar", "source": "construction", "confidence": 0.85, "aqi": 350},
        ]

    queue = []
    for h in hotspots:
        raw_source = h.get("source", "dust")
        source = _SOURCE_ALIAS.get(raw_source, raw_source)

        bundle = agent.recommend(
            ward=h["ward"],
            source=source,
            forecast_aqi=h["aqi"],
        )
        priority_score = round((h["aqi"] / 500) * h.get("confidence", 0.0), 2)

        queue.append({
            "id": h.get("id"),
            "ward": bundle.ward,
            "source": raw_source,
            "severity": bundle.severity,
            "actions": [
                {"action": a.action, "role": a.responsible_role, "urgency_hours": a.urgency_hours}
                for a in bundle.actions
            ],
            "priority_score": priority_score,
            "status": "Pending",
            "before_aqi": h["aqi"],
            "after_aqi": None,
        })

    queue.sort(key=lambda x: x["priority_score"], reverse=True)
    return {"queue": queue, "generated_at": datetime.utcnow().isoformat()}


# ---------- Feature: Outcome Tracking ----------

class OutcomePayload(BaseModel):
    queue_id: str
    before_aqi: int
    after_aqi: int

outcomes_store: dict = {}

@app.post("/api/enforcement-outcome")
def post_enforcement_outcome(payload: OutcomePayload):
    outcomes_store[payload.queue_id] = {
        "queue_id": payload.queue_id,
        "before_aqi": payload.before_aqi,
        "after_aqi": payload.after_aqi,
        "delta": payload.before_aqi - payload.after_aqi,
        "logged_at": datetime.utcnow().isoformat()
    }
    return {"success": True, "delta": payload.before_aqi - payload.after_aqi}


class ChatPayload(BaseModel):
    query: str
    ward: str
    language: str = "en"
    aqi: int
    source: str = "Unknown"
    confidence: float = 0.0
    risk_level: str = "Unknown"
    peak_month: str = "Unknown"
    weekday_delta: float = 0.0

@app.post("/api/chat")
def post_chat(payload: ChatPayload):
    try:
        agent = ExplanationAgent()
        context = {
            "ward": payload.ward,
            "aqi": payload.aqi,
            "source": payload.source,
            "confidence": round(payload.confidence * 100, 1),
            "risk_level": payload.risk_level,
            "peak_month": payload.peak_month,
            "weekday_delta": payload.weekday_delta
        }
        result = agent.answer(payload.query, context, payload.language)
        return result
    except Exception as e:
        return {"answer": "I'm having trouble connecting right now. Please check the AQI display for current conditions.", "citation": "", "language": payload.language}


@app.get("/")
def root():
    return {"status": "AirPulse features 2 (attribution), 5 (advisory), 10 (trends) are live"}

scheduler = BackgroundScheduler()
scheduler.add_job(run_ingestion, 'interval', minutes=30, id='ingestion_job')

@app.on_event("startup")
async def startup_event():
    scheduler.start()
    import logging
    logging.info("Ingestion scheduler started — running every 30 minutes")

@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown()
    import logging
    logging.info("Ingestion scheduler stopped")

@app.post("/api/ingest/trigger")
def trigger_ingestion_manual():
    try:
        run_ingestion()
        return {"success": True, "message": "Ingestion completed successfully"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/forecast/{ward}/multi-horizon")
def get_multi_horizon_forecast(ward: str):
    conditions = generate_current_conditions(ward)
    forecasts = prediction_agent.predict_multi_horizon(conditions)
    return [
        {
            "horizon_hr": f.horizon_hr,
            "predicted_aqi": f.predicted_aqi,
            "lower_bound": f.lower_bound,
            "upper_bound": f.upper_bound,
            "confidence": f.confidence,
        }
        for f in forecasts
    ]


@app.get("/api/forecast/model-report")
def get_forecast_model_report():
    return _prediction_metrics


# ---------- Feature 3: AI Intervention Recommendation Engine ----------

class RecommendationRequest(BaseModel):
    ward: str
    source: str  # traffic / construction / industrial / dust / stubble_burning
    forecast_aqi: float
    festival_context: Optional[str] = None


@app.post("/api/recommendations")
def get_recommendations(req: RecommendationRequest):
    bundle = recommendation_agent.recommend(
        ward=req.ward, source=req.source, forecast_aqi=req.forecast_aqi, festival_context=req.festival_context
    )
    return {
        "ward": bundle.ward,
        "source": bundle.source,
        "severity": bundle.severity,
        "forecast_aqi": bundle.forecast_aqi,
        "festival_context": bundle.festival_context,
        "actions": [
            {"action": a.action, "responsible_role": a.responsible_role, "urgency_hours": a.urgency_hours}
            for a in bundle.actions
        ],
    }


@app.get("/api/recommendations/{ward}")
def get_recommendations_from_pipeline(ward: str):
    """
    Convenience endpoint: chains attribution + forecast automatically to
    produce recommendations without the caller needing to run each agent
    manually first. Uses each ward's synthetic hotspot row for attribution.
    """
    import pandas as pd
    ward_hotspots = _training_df[_training_df["ward"] == ward]
    if ward_hotspots.empty:
        raise HTTPException(status_code=404, detail=f"No hotspot data for ward '{ward}'")
    attribution = attribution_agent.attribute(ward_hotspots.iloc[0])

    conditions = generate_current_conditions(ward)
    forecast = prediction_agent.predict(conditions, horizon_hr=24)

    bundle = recommendation_agent.recommend_from_attribution_and_forecast(attribution, forecast)
    return {
        "ward": bundle.ward,
        "attributed_source": attribution.predicted_source,
        "attribution_confidence": attribution.confidence,
        "forecast_aqi": forecast.predicted_aqi,
        "severity": bundle.severity,
        "actions": [
            {"action": a.action, "responsible_role": a.responsible_role, "urgency_hours": a.urgency_hours}
            for a in bundle.actions
        ],
    }


# ---------- Feature 4: Smart Enforcement Prioritization ----------

@app.get("/api/enforcement/queue")
def get_enforcement_priority_queue(top_n: int = 10):
    # Ward severity comes from the Prediction Agent's forecast for each ward.
    severity_map = {}
    for ward in _emission_sources_df["ward"].unique():
        conditions = generate_current_conditions(ward)
        forecast = prediction_agent.predict(conditions, horizon_hr=24)
        severity_map[ward] = recommendation_agent.severity_band(forecast.predicted_aqi)

    ranked = enforcement_agent.prioritize(_emission_sources_df, severity_map)
    return [
        {
            "source_id": r.source_id,
            "name": r.name,
            "ward": r.ward,
            "type": r.type,
            "priority_score": r.priority_score,
            "reasons": r.reasons,
        }
        for r in ranked[:top_n]
    ]


# ---------- Feature 11: Emergency Pollution Detection (ward-level convenience) ----------

@app.get("/api/emergency/check/{ward}")
def check_emergency(ward: str, simulate_spike: bool = False):
    """Ward-level convenience wrapper: generates a synthetic station reading
    series for the ward and runs the station-keyed spike detector."""
    series = generate_station_reading_series(station_id=hash(ward) % 1000, spike=simulate_spike)
    alert = emergency_agent.check_station(series)
    if alert is None:
        return {"ward": ward, "emergency": False}
    return {
        "ward": ward,
        "emergency": True,
        "timestamp": alert.timestamp,
        "pm25": alert.pm25,
        "aqi": alert.aqi,
        "zscore": alert.zscore,
        "trigger_types": alert.trigger_types,
        "priority": alert.priority,
        "message": alert.message,
    }


@app.get("/api/emergency/check-all")
def check_all_emergencies():
    from data.mock_data import WARDS
    # Generate one synthetic station per ward; Anand Vihar gets a spike
    readings_by_station = {
        i: generate_station_reading_series(station_id=i, spike=(ward == "Anand Vihar"))
        for i, ward in enumerate(WARDS, start=1)
    }
    ward_lookup = {i: ward for i, ward in enumerate(WARDS, start=1)}
    alerts = emergency_agent.check_all_stations(readings_by_station)
    return [
        {
            "ward": ward_lookup.get(a.station_id, f"Ward-{a.station_id}"),
            "station_id": a.station_id,
            "trigger_types": a.trigger_types,
            "aqi": a.aqi,
            "priority": a.priority,
            "message": a.message,
        }
        for a in alerts
    ]
