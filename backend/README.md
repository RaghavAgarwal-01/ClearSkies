# AirPulse — Features 1, 2, 3, 4, 5, 7, 11

Working implementations of seven system features from the AirPulse plan. (Note: an earlier version of this README called the trend agent "Feature 10" — it's actually **Feature 7** per Section 2 of the plan; #10 is Multi-city Comparison, not yet built.)

- **Feature 1 — Hyperlocal AQI Prediction** (`agents/prediction_agent.py`): LightGBM regressor forecasting AQI 24/48/72 hours ahead per ward, with widening confidence intervals for longer horizons.
- **Feature 2 — Pollution Source Attribution** (`agents/attribution_agent.py`): RandomForest classifier attributing hotspots to traffic/construction/industrial/dust/stubble-burning with confidence + evidence.
- **Feature 3 — AI Intervention Recommendation Engine** (`agents/recommendation_agent.py`): Deterministic source × severity decision matrix producing role-specific, time-bound actions (deliberately rule-based, not LLM-driven, for auditability).
- **Feature 4 — Smart Enforcement Prioritization** (`agents/enforcement_agent.py`): Ranks registered emission sources by a composite risk score (proximity to hotspot, permit status, inspection recency, forecast severity).
- **Feature 5 — Citizen Health Advisory** (`agents/advisory_agent.py`): Personalized, multilingual (English + Hindi, easily extendable) health advisories based on forecast AQI + vulnerability profile.
- **Feature 7 — Trend Analysis** (`agents/trend_agent.py`): Weekday/weekend deltas, monthly seasonality, festival-linked spikes, and statistical anomaly days.
- **Feature 11 — Emergency Pollution Detection** (`agents/emergency_agent.py`): Real-time rate-of-change + absolute-threshold detection on sub-hourly readings, independent of the daily Trend Analysis anomaly check.

All seven are wired into a FastAPI app (`api/main.py`) so the frontend team can integrate immediately.

## Setup

```bash
pip install -r requirements.txt
```

## Run each agent standalone (prints a demo result)

```bash
python3 agents/attribution_agent.py
python3 agents/advisory_agent.py
python3 agents/trend_agent.py
python3 agents/prediction_agent.py
python3 agents/recommendation_agent.py
python3 agents/enforcement_agent.py
python3 agents/emergency_agent.py
```

## Run the API

```bash
uvicorn main:app --reload --port 8000        # if you flattened main.py into backend/
# or
uvicorn api.main:app --reload --port 8000    # if api/main.py stayed nested
```

Then open `http://localhost:8000/docs` for interactive Swagger docs, or:

```bash
# Feature 1 — forecast
curl "http://localhost:8000/api/forecast/Ward-1?horizon_hr=48"
curl "http://localhost:8000/api/forecast/Ward-2/multi-horizon"

# Feature 2 — attribution
curl -X POST http://localhost:8000/api/attribution \
  -H "Content-Type: application/json" \
  -d '{"ward":"Ward-3","traffic_density_idx":0.2,"construction_permit_density":0.05,"industrial_stack_count":5,"thermal_anomaly_count":0,"dust_landuse_pct":0.05,"pm25":95}'

# Feature 3 — recommendations (manual or auto-piped from attribution+forecast)
curl -X POST http://localhost:8000/api/recommendations \
  -H "Content-Type: application/json" \
  -d '{"ward":"Ward-3","source":"industrial","forecast_aqi":420}'
curl "http://localhost:8000/api/recommendations/Ward-1"

# Feature 4 — enforcement queue
curl "http://localhost:8000/api/enforcement/queue?top_n=5"

# Feature 5 — advisory
curl -X POST http://localhost:8000/api/advisory \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u9","ward":"Ward-2","language":"hi","conditions":["asthma"],"forecast_aqi":320}'

# Feature 7 — trends
curl http://localhost:8000/api/trends/Ward-4
curl http://localhost:8000/api/trends

# Feature 11 — emergency detection
curl "http://localhost:8000/api/emergency/check/Ward-5?simulate_spike=true"
curl "http://localhost:8000/api/emergency/check-all"
```

## Connecting to Neon (real database)

Your live Neon schema already exists (`db/migrations/001_init_schema.sql` mirrors it — **don't re-run 001, it's reference only**). It's missing two things the agents need: a `citizens` table (for personalized advisories) and raw feature columns on `hotspots` (for attribution training/audit). Run the additive migration to add those without touching existing data:

1. Copy `.env.example` to `.env` and paste your Neon **pooled** connection string (Neon Console → your project → Connection Details). Keep `sslmode=require`.
2. Load it:
   ```bash
   export $(cat .env | xargs)
   ```
3. Run the additive migrations (psql, or the Python fallback if psql isn't installed):
   ```bash
   psql "$DATABASE_URL" -f db/migrations/002_add_attribution_and_citizens.sql
   # or, if psql isn't available (e.g. plain Git Bash on Windows):
   python db/run_migration.py db/migrations/002_add_attribution_and_citizens.sql
   python db/run_migration.py db/migrations/003_add_constraints_and_weather.sql
   python db/run_migration.py db/migrations/005_operational_data.sql
   ```
4. Seed at least one row in `citizens` so `/api/advisory` has someone real to look up (or keep passing profile fields directly in the request, which works without the table too).
5. Set `GROQ_API_KEY` in `backend/.env` to enable the RAG chat endpoint, then start the API. It uses live database data only and writes attribution, advisories, alerts, and outcomes back to Neon.

**Attribution model requirement:** the RandomForest classifier trains only on manually reviewed `source_label` rows. It reports unavailable instead of training on fabricated labels until there are enough reviewed examples.

**Forecast model requirement:** the model trains from observed readings and stored weather columns. It reports unavailable until enough complete daily rows have been ingested.

## Live data flow

The scheduled pipeline ingests CPCB readings (OpenAQ v3 is a keyed fallback), Open-Meteo weather, NASA FIRMS anomalies, and periodic OSM/Overpass land-use and road features. It rejects invalid records and never inserts random fallback readings. The frontend calls the live API routes; `data/mock_data.py` remains isolated to development examples only.
