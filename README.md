# Whale Tracker

Multi-chain, **read-only** whale wallet monitoring and analytics. It never asks for or stores private keys or seed phrases.

Single repository rooted here: `backend/` (FastAPI), `frontend/` (Next.js), `infra/` (nginx), `docker-compose.yml`.

## Status

| Done (tested) | Not built yet |
|---|---|
| FastAPI app, structured JSON logging, CORS, error envelope | Transaction ingestion / indexer integration, workers beyond `ping` |
| Health, chains, **auth** (register/login/me, Argon2id, JWT, per-IP rate limit), **wallet CRUD** (11-chain address validation, per-user isolation) | Classifier, whale detection, analytics/prices, alerts, AI |
| Alembic migrations 0001–0003 (users, wallets, transactions, sync checkpoints, classifications) | Adapters other than BNB (balances/tx lookup via RPC; not exposed by any API yet) |
| Next.js dashboard shell (Overview only) | Login/wallet pages, charts, live updates |
| Docker Compose: postgres, redis, backend, worker, frontend, nginx | CI, backups, HTTPS, metrics, token revocation / HttpOnly cookie sessions |

Other nav links are placeholders (404). Every chain in the registry is still `planned`: only BNB has adapter code, and nothing ingests data yet.

### Auth & wallet API (bearer tokens)
`POST /api/v1/auth/register` · `POST /api/v1/auth/login` · `GET /api/v1/auth/me` · `GET|POST /api/v1/wallets/` · `GET|DELETE /api/v1/wallets/{id}` — docs at `/api/docs`.
Passwords: 12–128 chars, Argon2id. Tokens last 30 min and are sent as `Authorization: Bearer`. Another user's wallet returns 404, never 403.
Limitations: no refresh/revocation, address validation checks format only (Bitcoin is mainnet-only), rate limiting is per IP and needs `TRUST_PROXY_HEADERS=true` behind nginx (set in compose; unpublish port 8000 in production).

After a fresh database volume, apply migrations once: `docker compose exec -T backend alembic upgrade head`.

## Run with Docker (PowerShell)

```powershell
cd E:\Wallet-Tracker
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
cd E:\Wallet-Tracker\backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000

# frontend (new terminal)
cd E:\Wallet-Tracker\frontend
npm install
npm run dev
```

## Verify

```powershell
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/health/ready
cd E:\Wallet-Tracker\backend; .\.venv\Scripts\python -m pytest -q
cd E:\Wallet-Tracker\frontend; npm run build
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
