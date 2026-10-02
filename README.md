# Whale Tracker

Multi-chain, **read-only** whale wallet monitoring and analytics. It never asks for or stores private keys or seed phrases.

Single repository rooted here: `backend/` (FastAPI), `frontend/` (Next.js), `infra/` (nginx), `docker-compose.yml`.

## Status — Phase 1 (foundation)

| Done | Pending |
|---|---|
| FastAPI app, structured JSON logging, CORS, error handlers | Auth, DB models, Alembic migrations (Phase 2) |
| `/api/v1/health`, `/api/v1/health/ready` (DB + Redis), `/api/v1/chains` | Ethereum/Solana adapters (Phase 3) |
| Celery worker skeleton (`system.ping` only) | Ingestion, classification, alerts (Phases 4–9) |
| Next.js dark dashboard shell, 12-item nav, live status/registry | shadcn/ui, Recharts, TradingView charts (Phase 7+) |
| Docker Compose: postgres, redis, backend, worker, frontend, nginx | AI insights, hardening (Phase 10) |

Only Overview exists as a page; other nav links are placeholders (404) until their phases. Chain registry entries are all `planned` — no chain is live.

## Run with Docker (PowerShell)

```powershell
cd D:\wallet
Copy-Item .env.example .env
docker compose up --build -d
docker compose ps
```

Open http://localhost (nginx) or http://localhost:3000. API docs: http://localhost/api/docs.

## Run locally without Docker

```powershell
# infra only
docker compose up -d postgres redis

# backend
cd D:\wallet\backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000

# frontend (new terminal)
cd D:\wallet\frontend
npm install
npm run dev
```

## Verify

```powershell
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/health/ready
cd D:\wallet\backend; .\.venv\Scripts\python -m pytest -q
cd D:\wallet\frontend; npm run build
```

## File guide

- `backend/app/main.py` — app factory, CORS, request logging middleware, error handlers
- `backend/app/core/` — `config.py` (env settings), `logging.py` (structlog), `redis.py`
- `backend/app/db/session.py` — async SQLAlchemy engine + probe
- `backend/app/chains/registry.py` — the 11 target networks and their implementation status
- `backend/app/api/v1/` — routers (`health`, `chains`)
- `backend/app/workers/celery_app.py` — Celery app
- `backend/tests/test_api.py` — API tests
- `frontend/app/` — layout and Overview page; `components/` sidebar, header, KPI card; `lib/api.ts` typed fetch
- `infra/nginx/nginx.conf` — reverse proxy (`/api`, `/ws`, `/`)
