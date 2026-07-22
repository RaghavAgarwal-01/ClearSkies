"""ClearSkies FastAPI application: live database-backed feature routes."""

import logging
import os
import sys
from datetime import datetime
from typing import Optional

import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

sys.path.append(os.path.dirname(__file__))

from agents.advisory_agent import CitizenAdvisoryAgent, CitizenProfile
from agents.alert_agent import RealTimeAlertAgent
from agents.analytics_agent import AnalyticsAgent
from agents.attribution_agent import PollutionAttributionAgent
from agents.chat_agent import ChatAssistantAgent
from agents.comparison_agent import MultiCityComparisonAgent
from agents.emergency_agent import EmergencyDetectionAgent
from agents.enforcement_agent import EnforcementPrioritizationAgent
from agents.explanation_agent import ExplanationAgent
from agents.heatmap_agent import HeatmapAgent
from agents.prediction_agent import AQIPredictionAgent
from agents.recommendation_agent import RecommendationAgent
from agents.trend_agent import TrendAnalysisAgent
from data.knowledge_corpus import DOCS
from data.mock_data import FESTIVALS_2025_26
from db.database import is_db_configured
from db import repository
from pipeline.ingestion import run_ingestion

logger = logging.getLogger(__name__)
app = FastAPI(title="ClearSkies API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

attribution_agent = PollutionAttributionAgent()
prediction_agent = AQIPredictionAgent()
advisory_agent = CitizenAdvisoryAgent()
trend_agent = TrendAnalysisAgent()
recommendation_agent = RecommendationAgent()
enforcement_agent = EnforcementPrioritizationAgent()
emergency_agent = EmergencyDetectionAgent()
heatmap_agent = HeatmapAgent()
comparison_agent = MultiCityComparisonAgent()
analytics_agent = AnalyticsAgent()
alert_agent = RealTimeAlertAgent()
chat_agent = ChatAssistantAgent(DOCS)
MODEL_STATUS = {"attribution": "not trained", "forecast": "not trained"}
scheduler = BackgroundScheduler()


def _real_db_or_503():
    if not is_db_configured():
        raise HTTPException(503, "DATABASE_URL is not configured. Live data is required for this endpoint.")


def _train_models():
    """Train only from observed/reviewed database records. No synthetic fallback is permitted."""
    if not is_db_configured():
        MODEL_STATUS.update({"attribution": "DATABASE_URL is not configured", "forecast": "DATABASE_URL is not configured"})
        return
    try:
        MODEL_STATUS["attribution"] = {"report": attribution_agent.train(repository.fetch_labeled_hotspot_features())}
    except Exception as exc:
        MODEL_STATUS["attribution"] = f"unavailable: {exc}"
    try:
        MODEL_STATUS["forecast"] = {"metrics": prediction_agent.train(repository.fetch_prediction_training_data())}
    except Exception as exc:
        MODEL_STATUS["forecast"] = f"unavailable: {exc}"


def _attribute_from_features(features: dict) -> tuple[str, float]:
    result = attribution_agent.attribute(pd.Series({"ward": "", **features}))
    return result.predicted_source, result.confidence


def _forecast_or_503(ward: str):
    if not prediction_agent._is_trained:
        raise HTTPException(503, f"Forecast model is {MODEL_STATUS['forecast']}. Ingest more complete observed readings.")
    conditions = repository.fetch_current_conditions(ward)
    if not conditions:
        raise HTTPException(404, f"No complete current conditions are available for '{ward}'.")
    return prediction_agent, conditions


def _record_alert_dispatch(dispatch) -> None:
    """Persist alert history without failing the user-facing response."""
    try:
        repository.insert_alert_log(
            dispatch.recipient, dispatch.channel, dispatch.message,
            dispatch.risk_level, dispatch.status,
        )
    except SQLAlchemyError:
        logger.warning(
            "Alert dispatch was not logged because alerts_log is unavailable; "
            "apply db/migrations/005_operational_data.sql."
        )


class HotspotInput(BaseModel):
    ward: str
    traffic_density_idx: float
    construction_permit_density: float
    industrial_stack_count: int
    thermal_anomaly_count: int
    dust_landuse_pct: float
    pm25: float
    hotspot_id: Optional[int] = None


class AdvisoryRequest(BaseModel):
    user_id: str
    ward: str
    language: str = "en"
    conditions: list[str] = []
    elderly: bool = False
    outdoor_worker: bool = False
    forecast_aqi: float


class OutcomePayload(BaseModel):
    queue_id: int
    before_aqi: int
    after_aqi: int
    action_taken: str = "Outcome logged"


class EnforcementStatusPayload(BaseModel):
    status: str


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


@app.get("/")
def root():
    return {"status": "ok", "data_mode": "live" if is_db_configured() else "database not configured", "models": MODEL_STATUS}


@app.get("/api/wards")
def get_wards():
    _real_db_or_503()
    return repository.fetch_ward_options()


@app.get("/api/hotspots")
def get_hotspots(ward: Optional[str] = None):
    _real_db_or_503()
    df = repository.fetch_active_hotspots_for_map(ward)
    if df.empty:
        return []
    df = df.loc[df.groupby("ward")["aqi"].idxmax()]
    return [{"id": str(row.hotspot_id), "zone": row.ward, "lat": float(row.lat), "lng": float(row.lon),
             "source": row.attributed_source or "unknown", "confidence": round(float(row.confidence_score or 0) * 100),
             "aqi": int(row.aqi or 0)} for row in df.itertuples()]


@app.get("/api/hotspots/{hotspot_id}/features")
def get_hotspot_features(hotspot_id: int):
    _real_db_or_503()
    hotspot = repository.fetch_hotspot_by_id(hotspot_id)
    if not hotspot:
        raise HTTPException(404, "Hotspot not found")
    return hotspot


@app.post("/api/attribution")
def attribute_hotspot(hotspot: HotspotInput):
    if not attribution_agent._is_trained:
        raise HTTPException(503, f"Attribution model is {MODEL_STATUS['attribution']}. Add reviewed hotspot labels.")
    result = attribution_agent.attribute(pd.Series(hotspot.model_dump(exclude={"hotspot_id"})))
    if hotspot.hotspot_id is not None and is_db_configured():
        repository.insert_hotspot_attribution(hotspot.hotspot_id, result.predicted_source, result.confidence)
    return {"ward": result.ward, "predicted_source": result.predicted_source, "confidence": result.confidence,
            "all_probabilities": result.all_probabilities, "evidence": result.evidence}


@app.get("/api/attribution/model-report")
def get_model_report():
    return MODEL_STATUS["attribution"]


@app.post("/api/advisory")
def get_advisory(req: AdvisoryRequest):
    profile = CitizenProfile(user_id=req.user_id, ward=req.ward, language=req.language, conditions=req.conditions,
                             elderly=req.elderly, outdoor_worker=req.outdoor_worker)
    advisory = advisory_agent.generate(profile, req.forecast_aqi)
    if is_db_configured():
        repository.insert_advisory(advisory.ward, advisory.language, advisory.message, advisory.risk_level)
        dispatch = alert_agent.dispatch_advisory(advisory.ward, advisory.risk_level, advisory.message)
        if dispatch:
            _record_alert_dispatch(dispatch)
    return {"user_id": advisory.user_id, "ward": advisory.ward, "language": advisory.language,
            "risk_level": advisory.risk_level, "forecast_aqi": advisory.forecast_aqi, "message": advisory.message}


@app.get("/api/trends/{ward}")
def get_ward_trends(ward: str):
    _real_db_or_503()
    history = repository.fetch_historical_aqi()
    if history.empty or ward not in history["ward"].unique():
        raise HTTPException(404, f"No historical readings for '{ward}'")
    report = trend_agent.analyze_ward(history, ward, FESTIVALS_2025_26)
    return {"ward": report.ward, "avg_aqi": report.avg_aqi, "weekday_avg": report.weekday_avg,
            "weekend_avg": report.weekend_avg, "weekday_vs_weekend_delta": report.weekday_vs_weekend_delta,
            "monthly_avg": report.monthly_avg, "peak_month": report.peak_month,
            "festival_spikes": report.festival_spikes, "anomaly_days": report.anomaly_days}


@app.get("/api/trends")
def get_all_trends():
    _real_db_or_503()
    history = repository.fetch_historical_aqi()
    if history.empty:
        return {}
    reports = trend_agent.analyze_all_wards(history, FESTIVALS_2025_26)
    return {ward: {"avg_aqi": report.avg_aqi, "peak_month": report.peak_month,
                   "festival_spikes": report.festival_spikes, "anomaly_count": len(report.anomaly_days)}
            for ward, report in reports.items()}


@app.get("/api/forecast/{ward}/multi-horizon")
def get_multi_horizon_forecast(ward: str):
    _real_db_or_503()
    agent, conditions = _forecast_or_503(ward)
    return [{"horizon_hr": result.horizon_hr, "predicted_aqi": result.predicted_aqi,
             "lower_bound": result.lower_bound, "upper_bound": result.upper_bound, "confidence": result.confidence}
            for result in agent.predict_multi_horizon(conditions)]


@app.get("/api/forecast/model-report")
def get_forecast_model_report():
    return MODEL_STATUS["forecast"]


@app.get("/api/recommendations/{ward}")
def get_recommendations_for_ward(ward: str):
    _real_db_or_503()
    hotspots = repository.fetch_active_hotspots_for_map(ward, limit=1)
    if hotspots.empty:
        raise HTTPException(404, f"No hotspot available for '{ward}'")
    agent, conditions = _forecast_or_503(ward)
    hotspot = hotspots.iloc[0]
    forecast = agent.predict(conditions)
    bundle = recommendation_agent.recommend(ward, hotspot.attributed_source or "unknown", forecast.predicted_aqi)
    return {"ward": ward, "attributed_source": hotspot.attributed_source or "unknown",
            "attribution_confidence": float(hotspot.confidence_score or 0), "forecast_aqi": forecast.predicted_aqi,
            "severity": bundle.severity, "actions": [{"action": action.action, "responsible_role": action.responsible_role,
            "urgency_hours": action.urgency_hours} for action in bundle.actions]}


@app.get("/api/enforcement-queue")
def get_dashboard_enforcement_queue():
    _real_db_or_503()
    queue = repository.fetch_dashboard_enforcement_queue()
    for item in queue:
        bundle = recommendation_agent.recommend(item["ward"], item["source"] or "unknown", item["before_aqi"])
        item["actions"] = [{"action": action.action, "role": action.responsible_role, "urgency_hours": action.urgency_hours}
                           for action in bundle.actions]
        item["action"] = item["actions"][0]["action"] if item["actions"] else "Investigate and validate the emission source."
    return {"queue": queue, "generated_at": datetime.utcnow().isoformat()}


@app.get("/api/enforcement/queue")
def get_prioritized_enforcement_queue(top_n: int = 10):
    _real_db_or_503()
    sources = repository.fetch_emission_sources()
    if sources.empty:
        return []
    severity = {}
    for ward in sources["ward"].unique():
        try:
            _, conditions = _forecast_or_503(ward)
            severity[ward] = recommendation_agent.severity_band(prediction_agent.predict(conditions).predicted_aqi)
        except HTTPException:
            severity[ward] = "moderate"
    return [{"source_id": item.source_id, "name": item.name, "ward": item.ward, "type": item.type,
             "priority_score": item.priority_score, "reasons": item.reasons}
            for item in enforcement_agent.prioritize(sources, severity)[:top_n]]


@app.post("/api/enforcement-outcome")
def post_enforcement_outcome(payload: OutcomePayload):
    _real_db_or_503()
    repository.insert_intervention(payload.queue_id, payload.before_aqi, payload.after_aqi, payload.action_taken)
    return {"success": True, "delta": payload.before_aqi - payload.after_aqi}


@app.patch("/api/enforcement/{queue_id}")
def patch_enforcement_status(queue_id: int, payload: EnforcementStatusPayload):
    _real_db_or_503()
    try:
        repository.update_enforcement_status(queue_id, payload.status)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"success": True, "status": payload.status}


@app.get("/api/heatmap")
def get_heatmap(city: Optional[str] = None):
    _real_db_or_503()
    snapshot = repository.fetch_latest_station_readings(city)
    result = heatmap_agent.interpolate(snapshot, city or "all", "aqi")
    return {"city": result.city, "pollutant": result.pollutant, "grid": result.grid, "stations": result.stations}


@app.get("/api/wards/geojson")
def get_ward_boundaries(city: Optional[str] = None):
    _real_db_or_503()
    return repository.fetch_ward_boundaries(city)


@app.get("/api/alerts")
def get_alerts(limit: int = 50):
    _real_db_or_503()
    try:
        return repository.fetch_recent_alerts(limit).to_dict("records")
    except SQLAlchemyError:
        logger.warning(
            "Alerts feed is unavailable because alerts_log is missing; "
            "apply db/migrations/005_operational_data.sql."
        )
        return []


@app.get("/api/emergency/check/{ward}")
def check_emergency(ward: str):
    _real_db_or_503()
    station_ids = repository.fetch_all_active_station_ids(ward_name=ward)
    for station_id in station_ids:
        series = repository.fetch_recent_readings(station_id)
        alert = emergency_agent.check_station(series)
        if alert:
            dispatch = alert_agent.dispatch_emergency(ward, alert.message)
            _record_alert_dispatch(dispatch)
            return {"ward": ward, "emergency": True, "station_id": alert.station_id, "aqi": alert.aqi,
                    "trigger_types": alert.trigger_types, "priority": alert.priority, "message": alert.message}
    return {"ward": ward, "emergency": False}


@app.get("/api/multi-city-comparison")
def get_multi_city_comparison(days: int = 30):
    _real_db_or_503()
    cities = repository.fetch_city_names()
    history = repository.fetch_multi_city_summary(cities, days)
    sources = repository.fetch_source_breakdown_by_city(cities, days)
    interventions = repository.fetch_intervention_summary(cities, days).set_index("city")
    entries = comparison_agent.compare(history.assign(intervention_logged=False, aqi_drop=0), sources)
    return [{"city": item.city, "avg_aqi": item.avg_aqi,
             "intervention_count": int(interventions.loc[item.city, "intervention_count"]) if item.city in interventions.index else 0,
             "avg_aqi_drop_per_intervention": float(interventions.loc[item.city, "avg_aqi_drop"]) if item.city in interventions.index and pd.notna(interventions.loc[item.city, "avg_aqi_drop"]) else 0,
             "source_breakdown": item.source_breakdown} for item in entries]


@app.get("/api/analytics")
def get_analytics(city: Optional[str] = None):
    _real_db_or_503()
    summary = analytics_agent.summarize(repository.fetch_enforcement_status_counts(city),
                                        repository.fetch_intervention_roi_timeseries(city),
                                        repository.fetch_source_breakdown_by_city([city], 60) if city else pd.DataFrame())
    return summary.__dict__


@app.post("/api/chat")
def post_chat(payload: ChatPayload):
    retrieved = chat_agent.retrieve(payload.query)
    context = {"ward": payload.ward, "aqi": payload.aqi, "source": payload.source,
               "confidence": round(payload.confidence * 100, 1), "risk_level": payload.risk_level,
               "peak_month": payload.peak_month, "weekday_delta": payload.weekday_delta}
    try:
        result = ExplanationAgent().answer(payload.query, context, payload.language, retrieved)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return {**result, "citations": [{"id": doc["id"], "title": doc["title"]} for doc in retrieved]}


@app.on_event("startup")
async def startup_event():
    _train_models()
    if is_db_configured():
        scheduler.add_job(lambda: run_ingestion(_attribute_from_features if attribution_agent._is_trained else None),
                          "interval", minutes=30, id="ingestion_job", replace_existing=True)
        scheduler.start()


@app.on_event("shutdown")
async def shutdown_event():
    if scheduler.running:
        scheduler.shutdown()
