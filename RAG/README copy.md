# Venture RAG Platform

FastAPI backend with Haystack 2 pipelines plus a React frontend for GPT-style customer-support Q&A across ingested company websites.

## Prerequisites

- Python 3.12
- Node.js 18+
- OpenAI API key (put in `.env` as `OPENAI_API_KEY=`)

## Backend Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Run API + UI

```bash
# activate the venv first
source .venv/bin/activate
# build the React frontend once (writes to app/static)
cd frontend && npm install && npm run build && cd ..
# start FastAPI (serves API + frontend)
uvicorn app.main:app --reload
```

Open http://localhost:8000/ to use the chat UI.

## Ingest a Website

```bash
curl -X POST http://localhost:8000/rag/ingest \
  -H "Content-Type: application/json" \
  -d '{"base_url": "https://example.com", "namespace": "example"}'
```

## Query via API

```bash
curl -X POST http://localhost:8000/rag/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What services do you offer?", "namespace": "example"}'
```

## Topic Guardrails (NeMo)

- We use [NVIDIA NeMo Guardrails](https://github.com/NVIDIA/NeMo-Guardrails) to block off-topic requests before the query pipeline runs.
- `data/topic_gate_dataset.csv` contains hand-labeled on/off-topic examples. At startup the service feeds up to `GUARDRAILS_EXAMPLES_PER_LABEL` samples per label into a tiny NeMo classifier.
- Configure the guard via `.env` (all optional):
  - `GUARDRAILS_ENABLED=true|false`
  - `GUARDRAILS_MODEL_ENGINE=openai`
  - `GUARDRAILS_MODEL=gpt-4o-mini` (or any NeMo-supported chat model)
  - `GUARDRAILS_DATASET_PATH=data/topic_gate_dataset.csv`
  - `GUARDRAILS_EXAMPLES_PER_LABEL=120`
- The input rail delegates to `app/guardrails/actions/actions.py`, which prompts the chosen model with few-shot examples derived from the dataset and returns an `ALLOW`/`DENY` verdict before the Haystack pipeline runs.
- If the NeMo dependency is missing, the app falls back to the legacy keyword filter so the API still works; install `nemoguardrails` and keep `OPENAI_API_KEY` set to enable the LLM-powered guard.

## Frontend Dev Workflow

```bash
cd frontend
npm install
npm run dev  # Vite dev server on http://localhost:5173
```

The dev server proxies API calls to http://localhost:8000.

## Project Layout

- `app/core` settings, logging, document store wiring
- `app/services` crawlers + preprocessing helpers
- `app/pipelines` ingestion/query flows
- `app/routers` FastAPI routes `/rag/*`
- `app/templates` + `app/static` bundled React UI

## Notes

- Default vector store is Chroma; configure Pinecone via `.env` when ready.
- Query responses are optimized for brevity: 2-3 bullet points plus references.
- `GET /rag/namespaces` returns available knowledge bases for the UI selector.

## Health Check

`GET /health` → `{ "status": "ok" }`
