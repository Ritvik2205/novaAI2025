# NOVA Multi-Tenant RAG Platform

Production-focused Retrieval-Augmented Generation stack for construction businesses. It ingests websites and uploaded files, labels and chunks content, indexes with hybrid dense/BM25 search, answers questions with citations, and qualifies/captures leads with quote ranges backed by a deterministic price book.

## Features
- Multi-tenant FastAPI service with API-key auth.
- Website crawler (robots-aware, optional Playwright rendering) plus PDF/DOCX/PPTX/CSV parsers.
- Layout-aware chunking, MinHash dedupe, multi-label classifier with LLM fallback.
- Hybrid retrieval (Elasticsearch BM25 + pgvector dense) with optional cross-encoder re-rank.
- Q&A and Lead/Quote agents with guardrails, CRM/email/calendar adapters, PDF quote generation.
- Celery ingestion workers, Redis queue/cache, Postgres 16 + pgvector, Elasticsearch 8.
- Price book rules engine with construction seed data.
- GitHub Actions CI (flake8 + pytest) and Dockerized deployment.

## Quickstart
```bash
make bootstrap
```
`make bootstrap` (see snippet below) provisions a virtual environment, installs dependencies + Playwright browsers, copies `.env`, runs migrations, seeds demo data, and starts docker-compose (Postgres, Elasticsearch, Redis, API, worker).

### Manual Steps
1. **Environment**
   ```bash
   python3.12 -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   playwright install --with-deps chromium
   cp .env.example .env
   ```
2. **Migrations**
   ```bash
   alembic upgrade head
   ```
3. **Seed price book**
   ```bash
   python scripts/seed_pricebook.py demo-construction pricebook/construction_pricebook.json
   ```
4. **Run services**
   ```bash
   docker compose -f docker/docker-compose.yaml up --build
   ```
   - API available on `http://localhost:8000`
   - Celery worker defined in compose file.

### FastAPI local dev (no containers)
```bash
uvicorn app.main:app --reload
```

Celery worker:
```bash
celery -A app.ingest.pipeline.celery_app worker --loglevel=info
```

## Environment Variables
| Key | Default | Notes |
| --- | --- | --- |
| `OPENAI_API_KEY` | empty | required for OpenAI providers |
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@db:5432/nova` | pgvector enabled |
| `ELASTIC_URL` | `http://elastic:9200` | Elasticsearch 8 |
| `REDIS_URL` | `redis://redis:6379/0` | broker + cache |
| `PLAYWRIGHT_BROWSE` | `0` | enable JS rendering |
| `EMBEDDING_PROVIDER` | `openai` | or `local` |
| `RERANK_ENABLED` | `true` | enable cross-encoder |
| `MAX_REFUND_CAP` | `5000` | guardrails |
| `MAX_QUOTE_CAP` | `250000` | guardrails |
| `DEFAULT_TIMEZONE` | `America/Los_Angeles` | scheduling |
| `API_HOST` | `http://api:8000` | workers hitting API |

See `.env.example` for full list & documentation.

## API Overview
All endpoints require `X-API-Key` (except tenant creation). JSON errors follow `{ "detail": "message" }`.

### 1. Create Tenant / API Key
```bash
curl -X POST http://localhost:8000/v1/tenants \
  -H "Content-Type: application/json" \
  -d '{"name":"Demo Construction","region":"west"}'
```
Response: `{ "tenant_id": 1, "api_key": "..." }`

### 2. Launch Website Ingest
```bash
curl -X POST http://localhost:8000/v1/ingest/website \
  -H "X-API-Key: <key>" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":1,"start_url":"https://example.com"}'
```
Returns `{ "job_id": "uuid" }`. Job status via `GET /v1/ingest/job/{job_id}`.

### 3. Upload Files
```bash
curl -X POST http://localhost:8000/v1/ingest/upload \
  -H "X-API-Key: <key>" \
  -F tenant_id=1 \
  -F files=@docs/brochure.pdf
```

### 4. Ask Questions
```bash
curl -X POST http://localhost:8000/v1/query \
  -H "X-API-Key: <key>" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":1,"query":"What warranties do you offer?","top_k":5,"rerank":true}'
```
Returns `{ "answer": "...", "citations": [...], "retrieved": [...] }`.

### 5. Lead Capture / Quote
```bash
curl -X POST http://localhost:8000/v1/lead/ask \
  -H "X-API-Key: <key>" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":1,"text":"Need a treehouse by June","dialog_state":{}}'
```
Follow with `POST /v1/lead/quote` once slots filled.

### 6. Pricebook Debug
```bash
curl -H "X-API-Key: <key>" http://localhost:8000/v1/pricebook/1
```
Admins can `POST` to update price rules.

### 7. Auth Check
```bash
curl -H "X-API-Key: <key>" http://localhost:8000/v1/auth/ping
```

## Minimal Postman Collection
```json
{
  "info": {
    "name": "NOVA RAG API",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "item": [
    {
      "name": "Create Tenant",
      "request": {
        "method": "POST",
        "header": [{"key":"Content-Type","value":"application/json"}],
        "body": {"mode":"raw","raw":"{\\"name\\":\\"Demo\\",\\"region\\":\\"west\\"}"},
        "url": "{{base}}/v1/tenants"
      }
    },
    {
      "name": "Query",
      "request": {
        "method": "POST",
        "header": [
          {"key":"X-API-Key","value":"{{api_key}}"},
          {"key":"Content-Type","value":"application/json"}
        ],
        "body": {"mode":"raw","raw":"{\\"tenant_id\\":1,\\"query\\":\\"pricing\\"}"},
        "url": "{{base}}/v1/query"
      }
    }
  ]
}
```

## Tests & CI
```bash
pytest
flake8
mypy app
```
GitHub Actions workflow `.github/workflows/ci.yaml` runs flake8 + pytest across pushes/PRs.

## Sample Data
- `pricebook/construction_pricebook.json`: Services, materials, adders, etc., used by `scripts/seed_pricebook.py`.
- `web-sample/`: Three HTML pages for crawler demos and ingest tests.

## Makefile Snippet (optional)
```makefile
bootstrap:
	python3.12 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]" && \
	playwright install --with-deps chromium && \
	cp -n .env.example .env || true && \
	alembic upgrade head && \
	python scripts/seed_pricebook.py demo-construction pricebook/construction_pricebook.json && \
	docker compose -f docker/docker-compose.yaml up --build
```

## Notes
- Agents, pipelines, and search helpers are organized under `app/` by domain for clarity.
- Guardrails middleware masks PII in logs, enforces action caps, and routes policy-sensitive requests.
- Embedding & LLM providers implement interfaces so you can drop in local models.
- Retrieval caches embeddings + LLM responses to control cost (Redis-based).
