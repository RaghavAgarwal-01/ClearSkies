# ClearSkies

> **From monitoring to movement.** ClearSkies is an AI-assisted urban air-quality intelligence platform that turns station readings into ward-level forecasts, source-attributed hotspots, recommended interventions, citizen advisories, and operational follow-up.

Built for the ET AI Hackathon 2026 implementation plan, ClearSkies focuses on the gap between knowing that air quality is poor and knowing what a city team should do next.

## Why ClearSkies

Most AQI products stop at a number or city-wide forecast. ClearSkies is designed as a decision-support loop:

```text
Observe -> validate and enrich -> forecast and attribute -> recommend
       -> notify citizens and officials -> track outcomes -> improve decisions
```

It provides separate experiences for municipal users and citizens while keeping the same live air-quality context underneath.

## What is implemented

| Plan capability | ClearSkies implementation |
| --- | --- |
| Hyperlocal AQI prediction | LightGBM-based 24, 48, and 72 hour ward forecasts with confidence bounds. |
| Source attribution | Random Forest classification of hotspots using traffic, construction, industrial, thermal-anomaly, dust, and PM2.5 features. |
| Intervention recommendations | Auditable source x severity rules produce time-bound actions and responsible roles. |
| Enforcement prioritisation | Risk-ranked enforcement queue plus outcome logging for before/after AQI. |
| Citizen advisory | English and Hindi risk guidance tailored to ward and vulnerability profile. |
| Geospatial intelligence | Leaflet maps with live hotspots, ward boundaries, and interpolated heatmap support. |
| Trend analysis | Historical average, seasonality, weekday/weekend deltas, festival spikes, and anomaly days. |
| Explanation assistant | Retrieval-backed air-quality Q&A with ward context and citations. |
| Alerts | Advisory and emergency alert dispatches recorded in an in-app alert feed. |
| Multi-city comparison | City benchmarks for AQI and intervention performance. |
| Emergency detection | Absolute threshold, rate-of-change, and rolling z-score checks on station readings. |
| Analytics | Intervention counts, AQI improvement, action performance, and recent-alert views. |

## User experiences

- **Dashboard** - city AQI, highest-risk hotspots, ward severity list, map, and recommended actions. The AQI tabs filter the live ward and hotspot view by CPCB band.
- **Forecast** - ward selector and 24/48/72-hour forecast chart with confidence interval and historical trend summary.
- **Hotspots** - map and list of active hotspots with source, confidence, AQI band, and available attribution evidence.
- **Admin Panel** - enforcement work queue and intervention outcome capture.
- **Analytics and Alerts** - city comparison, operational KPIs, and the in-app advisory feed.
- **Citizen Portal** - plain-language advisory, vulnerable-group guidance, ward selection, English/Hindi support, and a floating explanation chat window.

## Architecture

```text
CAAQMS / OpenAQ / weather / OSM / FIRMS
                 |
                 v
     scheduled ingestion and feature engineering
                 |
                 v
        PostgreSQL + PostGIS / Neon database
                 |
                 v
 FastAPI agent layer
   prediction | attribution | recommendations | advisories
   trends     | alerts      | emergency checks | analytics
                 |
                 v
       React + Vite + Leaflet web application
```

The backend is intentionally modular: each capability is implemented as a focused agent in `backend/agents/`, and the FastAPI application composes them into API routes. Scheduled ingestion refreshes live data on a 30-minute interval when the backend is running.

## Technology stack

| Layer | Technology |
| --- | --- |
| Web app | React 19, Vite, React Router |
| Maps and charts | React Leaflet / Leaflet, Recharts |
| API | FastAPI, Pydantic, Uvicorn |
| Data and ML | pandas, NumPy, scikit-learn, LightGBM |
| Database | PostgreSQL / Neon, PostGIS, SQLAlchemy, psycopg2 |
| Scheduling | APScheduler |
| Data inputs | CAAQMS/OpenAQ-compatible ingestion, Open-Meteo, OSM/Overpass, NASA FIRMS-ready feature pipeline |

## Repository layout

```text
ClearSkies/
├── frontend/
│   ├── src/pages/          # Dashboard, Forecast, Hotspots, Admin, Citizen
│   ├── src/components/     # Layout, maps, UI primitives, chat UI
│   ├── src/api/            # Frontend API client
│   └── package.json
├── backend/
│   ├── agents/             # Prediction, attribution, advisory, alert, analytics, etc.
│   ├── pipeline/           # Ingestion, seed data, OSM/Overpass helpers
│   ├── db/                 # Repository layer, migrations, migration runner
│   ├── data/               # Knowledge corpus and local development data
│   ├── main.py             # FastAPI application
│   └── requirements.txt
└── README.md
```

## Run locally

### Prerequisites

- Node.js 20+ and npm
- Python 3.11+
- A PostgreSQL/Neon database with PostGIS for live data

> **Repository note:** before starting the API, ensure `backend/main.py` has no unresolved Git conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`). The current working tree contains a pending merge section in that file, and Python cannot start until it is resolved.

### 1. Configure the backend

Create `backend/.env` with your database connection string:

```env
DATABASE_URL=postgresql://USER:PASSWORD@HOST/DATABASE?sslmode=require
```

Create and activate a virtual environment, then install dependencies:

```powershell
cd backend
py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Apply the schema migrations to a fresh database in this order:

```powershell
python db\run_migration.py db\migrations\001_init_schema.sql
python db\run_migration.py db\migrations\002_add_attribution_and_citizens.sql
python db\run_migration.py db\migrations\003_add_constraints_and_weather.sql
python db\run_migration.py db\migrations\005_operational_data.sql
```

`001_init_schema.sql` is a reference schema for the existing shared Neon database; do not re-run it against an already provisioned project. The remaining migrations are additive and safe to re-run.

Start the API:

```powershell
uvicorn main:app --reload --port 8000
```

The interactive API documentation is available at <http://localhost:8000/docs>.

### 2. Start the frontend

Open another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>.

To point the frontend to another API base URL, create `frontend/.env`:

```env
VITE_API_URL=http://localhost:8000
```

## Key API routes

| Area | Route |
| --- | --- |
| Health | `GET /` |
| Live hotspots | `GET /api/hotspots` |
| Source attribution | `POST /api/attribution` and `GET /api/attribution/model-report` |
| Forecast | `GET /api/forecast/{ward}/multi-horizon` |
| Recommendations | `POST /api/recommendations` and `GET /api/recommendations/{ward}` |
| Citizen advisory | `POST /api/advisory` |
| Trends | `GET /api/trends` and `GET /api/trends/{ward}` |
| Enforcement | `GET /api/enforcement-queue`, `GET /api/enforcement/queue`, `POST /api/enforcement-outcome` |
| Explanation chat | `POST /api/chat` |
| Emergency checks | `GET /api/emergency/check/{ward}`, `GET /api/emergency/check-all` |
| Ingestion | `POST /api/ingest/trigger` |

Route availability is documented by the running FastAPI instance at `/docs`.

## Attribution training requirement

The source-attribution model deliberately trains only on complete, manually reviewed hotspot rows. It needs at least two reviewed examples in each of two source categories before it can serve live predictions.

Each training row requires these fields:

```text
traffic_density_idx, construction_permit_density, industrial_stack_count,
thermal_anomaly_count, dust_landuse_pct, pm25, source_label
```

Review and label records in the database using genuine source evidence, then restart the API so the model can train. Stored model predictions should not be reused as ground truth.

## Development commands

```powershell
# Frontend production build and lint
cd frontend
npm run build
npm run lint
```

## Production roadmap

The hackathon MVP already provides the decision-support workflow. The implementation plan's next production steps are:

1. Add validated, human-reviewed attribution labels and continuous model evaluation.
2. Replace local/polled refresh with resilient queues, caching, and observability.
3. Connect real notification gateways for SMS, IVR, and push delivery.
4. Extend regional-language support and citizen notification preferences.
5. Add municipal ticketing integrations and role-based approvals before enforcement action.
6. Scale PostGIS data partitions and model monitoring across NCAP cities.

## Principles

- **Decision support, not automated enforcement.** Recommendations and source attribution require human review before action.
- **Explainable outputs.** Attribution confidence and feature evidence are shown instead of unsupported certainty.
- **Open-data first.** The architecture is designed around public or free-tier environmental, weather, and geospatial sources.
- **Citizen-first communication.** Advisories convert AQI values into practical guidance for vulnerable groups.

---

Built for the ET AI Hackathon 2026 implementation plan: a reusable urban air-quality intelligence layer for faster, evidence-backed intervention.
