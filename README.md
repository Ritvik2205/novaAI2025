# ScottyLabs Agentic CRM

Agentic CRM for ScottyLabs that learns how the organization matches student teams with partner projects, captures institutional knowledge, and routes inbound leads. The system is composed of:

- **Chat-style onboarding** – an AI concierge interviews ScottyLabs staff, requests documents, and writes to the knowledge base in real time.
- **Student group directory** – auto-generated profiles (focus areas, past work, availability, contacts) used for smart stakeholder matching.
- **Knowledge curation** – agents segment onboarding output into shareable or internal-only sections.
- **Lead board** – concierge + monitor agents qualify partner enquiries and progress them through new → engaged → qualified → quoted → won/lost.
- **Agentuity deployment** – the orchestrator can be hosted as a long-running Agentuity agent with built-in scaling, logging, and routing.

---

## Quickstart

### 1. Install dependencies
```bash
cd /Users/ritvikgupta/NOVA
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cd frontend
pnpm install    # or npm install
```

### 2. Environment variables (`.env` at repo root)
```bash
OPENROUTER_API_KEY=...
AGENTUITY_API_KEY=...
AGENTUITY_BASE_URL=https://api.agentuity.com/v1
```
Optional overrides: `OPENROUTER_BASE_URL`, `OPENROUTER_DEFAULT_MODEL`, `CALENDAR_PROVIDER`, `CALENDAR_CREDENTIALS_PATH`.

### 3. Run locally
```bash
# Flask backend (API + RAG services)
python main.py

# Frontend (React dashboard with Vite)
cd frontend
pnpm dev
```
Visit `http://localhost:5173` to access the multi-page console.

---

## Operator Console

| Page | Purpose |
|------|---------|
| **Onboarding chat** | Conversational UI that collects ScottyLabs knowledge, requests documents, and stores everything in the RAG store. Transcript is preserved and documents can be uploaded inline per question. |
| **Student groups** | Directory of all student teams discovered during onboarding, including expertise, recent projects, availability, and contacts. |
| **Knowledge base** | An agent reorganises captured information into sections. Operators decide which sections remain internal before saving visibility preferences. |
| **Lead board** | Pipeline view grouped by status (new, engaged, qualified, quoted, won, archived) driven by the action-monitoring agent’s structured updates. |

---

## Key API Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /api/company/session` | (Re)starts ScottyLabs onboarding; generates chat questions and kicks off crawling. |
| `POST /api/company/session/<session_id>/answer` | Streams answers back to the onboarding agent and accumulates insights, student groups, and document requests. |
| `POST /api/company/<id>/documents` | Uploads supporting assets (used by the chat UI). |
| `GET /api/company/<id>/groups` | Returns the student group directory. |
| `GET /api/company/<id>/knowledge/sections` | Invokes the knowledge architect agent to section the knowledge base. |
| `POST /api/company/<id>/knowledge/visibility` | Saves which sections should stay internal. |
| `POST /api/leads/message` | Handles inbound partner messages (auto-selects ScottyLabs if `company_id` omitted). |
| `GET /api/leads?company_id=<id>` | Lists leads for the pipeline view. |

All responses are JSON; 400/404 errors return `{ "error": "..." }`.

---

## Agentuity Deployment

The repository is ready for Agentuity.

- `agentuity.yaml` – project metadata, bundler configuration, and agent list.
- `agentuity_agents/scottylabs_orchestrator/agent.py` – Agentuity entry point wrapping the orchestrator.

### Deploy
1. Install the Agentuity CLI and authenticate:
   ```bash
   curl -fsSL https://get.agentuity.com/cli.sh | bash
   agentuity login
   ```
2. Export project keys:
   ```bash
   export AGENTUITY_SDK_KEY=...
   export AGENTUITY_PROJECT_KEY=...
   ```
3. Deploy:
   ```bash
   agentuity deploy
   ```
4. Invoke the hosted agent:
   ```bash
   agentuity invoke agent_scottylabs_orchestrator --json '{
     "action": "start_onboarding",
     "data": {"name": "ScottyLabs"}
   }'
   ```
   Supported actions: `start_onboarding`, `answer_onboarding`, `handle_lead`, `knowledge_sections`, `update_visibility`, `list_groups`, `list_leads`.

---

## Project Layout

```
backend/
  agents/               # Pydantic-based agents (onboarding, lead concierge, quote, monitor)
  repositories/         # JSON persistence (companies, student groups, leads, meetings, quotes)
  services/             # OpenRouter client, Agentuity client, RAG service, scheduler
  routers/              # Flask blueprints for company + lead APIs
frontend/
  src/components/
    CompanyConsole.tsx  # Multi-page operator console
    OnboardingWizard.tsx# Chat-style onboarding interface
    LeadBoard.tsx       # Pipeline view by status
agentuity_agents/
  scottylabs_orchestrator/agent.py  # Agentuity runtime entry point
```

---

## Tooling & Testing

- `python -m compileall backend agentuity_agents` – quick syntax check.
- `pnpm lint` / `pnpm build` – frontend validation.
- `agentuity deploy --dry-run` – validate Agentuity packaging without deploying.

---

## Next Steps

- Support direct document ingestion via Agentuity (base64 payloads) in addition to HTTP uploads.
- Add analytics dashboards for student group utilisation and win/loss trends.
- Integrate real calendar providers inside `CalendarService`.

---

Questions? Use the Agentuity CLI (`agentuity logs`) or console to observe the orchestrator once deployed.
