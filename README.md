# NexMarket AI — AI-Powered Marketing Automation Platform

> **College Demo Ready · Production Style · End-to-End AI Pipeline**

---

## What It Does

Submit a product → NexMarket AI automatically:
1. **Generates a marketing poster** (Stable Diffusion XL local / DALL·E 3 / Mock SVG)
2. **Generates channel-specific ad copy** (Qwen 2.5 Instruct local / GPT-4o / Demo templates)
3. **Evaluates the poster** using Vision LLM (Qwen2.5-VL local / GPT-4o)
4. **Predicts engagement** using LSTM forecasting (7–30 day horizon)
5. **Scores leads** using XGBoost (hot/warm/cold with feature importance)
6. **Optimizes campaign strategy** via Thompson Sampling contextual bandit
7. **Auto-posts to social media** (Instagram, Facebook, LinkedIn, Twitter — with mock mode)
8. **Orchestrates everything through n8n** (webhooks, polling, scheduling, retries)
9. **Shows results in a real-time dashboard** (Recharts, stats, forecasts)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Next.js Frontend                         │
│  Dashboard · Campaign Form · Poster Preview · Analytics Charts   │
└──────────────────────────┬──────────────────────────────────────┘
                           │ REST API
┌──────────────────────────▼──────────────────────────────────────┐
│                        FastAPI Backend                           │
│                                                                  │
│  /campaigns  /posters  /adcopy  /posting  /sentiment            │
│  /leads      /forecast /optimize /analytics /n8n                │
│                                                                  │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────────────┐ │
│  │ Poster Gen   │  │ Ad Copy Gen   │  │ Poster Evaluator     │ │
│  │ SDXL/Mock    │  │ Qwen2.5/GPT-4o│  │ Qwen2.5-VL / GPT-4o  │ │
│  └──────────────┘  └───────────────┘  └──────────────────────┘ │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────────────┐ │
│  │ Sentiment    │  │ Lead Scoring  │  │ LSTM Forecasting     │ │
│  │ DistilBERT   │  │ XGBoost       │  │ PyTorch LSTM         │ │
│  └──────────────┘  └───────────────┘  └──────────────────────┘ │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Social Posting Service                                    │   │
│  │ Instagram · Facebook · LinkedIn · Twitter · Mock         │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                PostgreSQL (via SQLAlchemy async)                  │
└─────────────────────────────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                       n8n Orchestrator                           │
│   Webhook → Trigger Pipeline → Poll Status → Ingest Analytics    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Stack

| Layer       | Technology                                        |
|-------------|---------------------------------------------------|
| Frontend    | Next.js 14, React, Tailwind CSS, Recharts         |
| Backend     | FastAPI, Python 3.11, SQLAlchemy (async)          |
| Database    | PostgreSQL 16                                     |
| Workflow    | n8n                                               |
| LLM         | Qwen 2.5 Instruct (local) / OpenAI GPT-4o         |
| Image Gen   | Stable Diffusion XL (local) / DALL·E 3            |
| Vision      | Qwen2.5-VL (local) / GPT-4o Vision                |
| Sentiment   | DistilBERT (HuggingFace Transformers)             |
| Lead ML     | XGBoost (trained on synthetic data)               |
| Forecasting | LSTM (pure PyTorch — NO GRU, NO TensorFlow)        |
| Optimization| Thompson Sampling Contextual Bandit               |
| Social Post | Meta Graph API / LinkedIn API / Tweepy / Mock     |

---

## Project Structure

```
NexMarket/
├── backend/
│   ├── app/
│   │   ├── api/v1/endpoints/     # All FastAPI routers
│   │   ├── core/                 # Config, logging
│   │   ├── db/                   # SQLAlchemy engine + session
│   │   ├── models/               # ORM models
│   │   ├── schemas/              # Pydantic v2 schemas
│   │   ├── services/
│   │   │   ├── ai/               # poster_generator, ad_generator,
│   │   │   │                     #   poster_evaluator, sentiment,
│   │   │   │                     #   lead_prediction, lstm_forecast
│   │   │   ├── posting/          # adapters + posting_service
│   │   │   └── optimization/     # Thompson Sampling optimizer
│   │   ├── prompts/              # All LLM prompt templates
│   │   └── main.py               # FastAPI app entry
│   ├── ml/lstm/                  # LSTM model weights
│   ├── ml/xgboost_model/         # XGBoost model weights
│   ├── assets/posters/           # Generated poster files
│   ├── alembic/                  # DB migrations
│   ├── tests/                    # Pytest test suite
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── app/                  # Next.js App Router pages
│   │   ├── components/           # Sidebar, charts, UI
│   │   └── lib/api.ts            # TypeScript API client
│   ├── package.json
│   ├── tailwind.config.js
│   └── Dockerfile
├── n8n/
│   └── workflows/                # n8n workflow JSON files
└── docker/
    └── docker-compose.yml
```

---

## Quick Start (Local)

### Prerequisites
- Python 3.11+
- Node.js 20+
- PostgreSQL 16 (or Docker)
- n8n (optional — for orchestration demo)

### 1. Database Setup
```bash
# Using Docker
docker run -d \
  -e POSTGRES_USER=nexmarket \
  -e POSTGRES_PASSWORD=nexmarket \
  -e POSTGRES_DB=nexmarket_db \
  -p 5432:5432 postgres:16-alpine

# Or install PostgreSQL locally and create:
# psql -c "CREATE USER nexmarket WITH PASSWORD 'nexmarket';"
# psql -c "CREATE DATABASE nexmarket_db OWNER nexmarket;"
```

### 2. Backend Setup
```bash
cd backend

# Copy and configure environment
cp .env.example .env
# Edit .env — set OPENAI_API_KEY, etc. (leave defaults for demo mode)

# Install dependencies
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Start server
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend Setup
```bash
cd frontend

# Install dependencies (requires internet)
npm install

# Start dev server
npm run dev
```

### 4. n8n Setup (Optional)
```bash
# Using Docker
docker run -d -p 5678:5678 \
  -e N8N_BASIC_AUTH_ACTIVE=true \
  -e N8N_BASIC_AUTH_USER=admin \
  -e N8N_BASIC_AUTH_PASSWORD=nexmarket123 \
  docker.n8n.io/n8nio/n8n

# Open http://localhost:5678
# Import: n8n/workflows/campaign_pipeline.json
```

### 5. Full Docker Stack
```bash
cd docker
docker-compose up -d
```

---

## API Reference

| Method | Endpoint                                | Description                        |
|--------|-----------------------------------------|------------------------------------|
| POST   | /api/v1/campaigns/                      | Create campaign                    |
| GET    | /api/v1/campaigns/                      | List campaigns                     |
| GET    | /api/v1/campaigns/{id}                  | Get campaign                       |
| POST   | /api/v1/posters/generate                | Generate poster (DALL·E/Mock)      |
| POST   | /api/v1/posters/{id}/evaluate           | Vision LLM evaluation              |
| POST   | /api/v1/adcopy/generate                 | Generate ad copy (all platforms)   |
| POST   | /api/v1/posting/publish                 | Publish to social media            |
| GET    | /api/v1/posting/health/platforms        | Check platform credentials         |
| POST   | /api/v1/sentiment/analyze               | Batch sentiment analysis           |
| POST   | /api/v1/leads/predict                   | XGBoost lead scoring               |
| POST   | /api/v1/forecast/                       | LSTM engagement forecast           |
| POST   | /api/v1/optimize/                       | Thompson Sampling optimization     |
| GET    | /api/v1/analytics/dashboard             | Dashboard summary                  |
| POST   | /api/v1/analytics/campaign/{id}/seed-demo | Seed 14 days of demo analytics  |
| POST   | /api/v1/n8n/trigger/campaign            | n8n pipeline trigger               |
| GET    | /api/v1/n8n/status/{campaign_id}        | n8n pipeline status poll           |
| POST   | /api/v1/n8n/analytics/ingest            | n8n analytics data push            |

Full Swagger UI: **http://localhost:8000/docs**

---

## Demo Flow (Viva)

1. **Open Dashboard** → http://localhost:3000 — show stats and chart
2. **Create Campaign** → Fill form for "CloudNotes Pro, 50% off, students" → toggle auto-pipeline ON
3. **Show poster** → AI-generated SVG/image with Vision evaluation radar chart
4. **Show ad copies** → Platform-specific variants (Instagram, LinkedIn, email)
5. **Show posting tab** → Mock post published instantly with ID and URL
6. **Show forecast** → LSTM 7-day engagement forecast chart
7. **Show optimization** → Thompson Sampling platform scores + recommendation
8. **Open n8n** → http://localhost:5678 → import and show workflow
9. **Trigger via n8n** → POST to webhook → watch status update live
10. **Show Swagger** → http://localhost:8000/docs → demo any endpoint live

---

## Demo Mode (No API Keys Required)

Set in `.env`:
```
SOCIAL_MODE=mock
IMAGE_PROVIDER=mock
LLM_PROVIDER=openai         # Will fall back if key missing
OPENAI_API_KEY=             # Empty = fallback to demo templates
```

With these settings:
- Posters are generated as SVG placeholders
- Ad copy uses template-based generation
- Poster evaluation uses mock scores
- Social posting uses mock adapter (fake IDs)
- ML models (XGBoost/LSTM) train on synthetic data on first run

---

## Environment Variables Reference

| Variable              | Default    | Description                            |
|-----------------------|------------|----------------------------------------|
| OPENAI_API_KEY        | (empty)    | OpenAI key for GPT-4o + DALL·E         |
| GEMINI_API_KEY        | (empty)    | Google Gemini key                      |
| LLM_PROVIDER          | local      | openai, gemini, or local               |
| IMAGE_PROVIDER        | local      | openai, stability, mock, or local      |
| SOCIAL_MODE           | mock       | live or mock                           |
| META_ACCESS_TOKEN     | (empty)    | Meta Graph API token                   |
| LINKEDIN_ACCESS_TOKEN | (empty)    | LinkedIn API token                     |
| TWITTER_API_KEY       | (empty)    | Twitter/X API key                      |
| DATABASE_URL          | local pg   | PostgreSQL async URL                   |

---

## Running Tests

```bash
cd backend
pytest tests/ -v
```

Tests cover: health check, campaign CRUD, sentiment analysis, lead scoring,
poster generation (mock), campaign optimization.

---

## Key Design Decisions

1. **LSTM only** for forecasting — no GRU anywhere
2. **Adapter pattern** for social posting — clean separation, easy to add platforms
3. **Mock-first** — everything works without API keys for demo
4. **n8n as orchestrator only** — all AI logic stays in FastAPI services
5. **Async FastAPI** — non-blocking poster/adcopy generation with BackgroundTasks
6. **Synthetic data bootstrap** — XGBoost and LSTM train on first run if no saved model
7. **Thompson Sampling** — interpretable contextual bandit for optimization
8. **Structlog** — JSON logs in production, pretty in dev

---

## Modules Summary

| Module | Implementation                    | Fallback                    |
|--------|-----------------------------------|-----------------------------|
| Poster Generator | Stable Diffusion XL local | SVG mock                    |
| Ad Generator     | Qwen 2.5 Instruct (local) | Template strings            |
| Poster Evaluator | Qwen2.5-VL (local)         | Mock scores                 |
| Sentiment        | DistilBERT                 | Keyword rules               |
| Lead Prediction  | XGBoost (synthetic train)  | Heuristic formula           |
| Forecasting      | LSTM (PyTorch, synthetic)  | Linear trend extrapolation  |
| Optimization     | Thompson Sampling Bandit   | Static platform priors      |
| Social Posting   | Meta/LinkedIn/Twitter APIs | Mock adapter                |
| Orchestration    | n8n + FastAPI webhooks     | Direct API calls            |
