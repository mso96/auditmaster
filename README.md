# AuditMaster

Working space for an enterprise internal audit team. The auditor always makes the final decision. Every AI output is designed to show the sources it used.

This repository is the initial scaffold. It does not generate a risk control matrix, recommend tests, or analyze spreadsheets yet.

## Product direction

1. **AI Risk Control Matrix (RCM).** From past audit reports, findings, company procedures, and audit standards (via retrieval), produce risks, related controls, and suggested audit tests. Each item cites its sources.
2. **AI test plan recommendations.** For each risk and control, suggest the data required and the steps to follow. Recommendations only.
3. **Later:** an analyst over uploaded Excel/CSV files (duplicate payments, anomalies), then a read-only database connection.

## Architecture

```
apps/web          Next.js App Router, TypeScript, Tailwind, shadcn/ui
services/api      Python FastAPI. RAG and the pandas/DuckDB engine will live here
Postgres          pgvector, for audit metadata and embeddings
```

The UI and the API are separate processes. The browser talks to the API over HTTP. Python owns retrieval and tabular analysis so those libraries stay off the Node side. There is no shared package yet; one can be added when a contract needs to be generated for both sides.

### Cloud now, on-prem later

The MVP runs in the cloud on synthetic data. The product that follows must run fully on-prem, including an air-gapped network with a local LLM. The scaffold only uses components that can be self-hosted:

- Next.js and FastAPI are ordinary containers.
- Postgres with pgvector is a standard image.
- The model is reached through an OpenAI-compatible HTTP API. `OPENAI_BASE_URL`, `OPENAI_MODEL`, and `OPENAI_API_KEY` select the server. The same client can later point at vLLM or Ollama. Nothing in the API calls a proprietary SDK that only works in one vendor's cloud.

No object store, queue, or hosted model is wired in. Those can be added later only if they also have an on-prem path.

## Run locally

Requirements: Docker with Compose, or Node.js 22 and Python 3.12 if you run the processes yourself.

### Docker Compose

```bash
cp .env.example .env   # optional; compose has the same local defaults
docker compose up --build
```

- Web: http://localhost:3000
- API health: http://localhost:8000/health
- API readiness (Postgres and pgvector): http://localhost:8000/ready
- Postgres: `localhost:5432`, database `auditmaster`, user `auditmaster`

The password in `.env.example` is a local default. Change it before using the stack anywhere else. Do not commit `.env`.

Postgres starts empty aside from the `vector` extension. This scaffold does not load synthetic documents, findings, or audit records.

`NEXT_PUBLIC_API_URL` is read when the web image is built, because the browser calls the API directly. The default `http://localhost:8000` matches the published API port.

### Without Docker

Start Postgres 16 with pgvector yourself and run `infra/postgres/init.sql`, or start only the database:

```bash
docker compose up db
```

API:

```bash
cd services/api
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
export OPENAI_BASE_URL=http://localhost:11434/v1
export OPENAI_API_KEY=local-dev
export OPENAI_MODEL=local-model
export DATABASE_URL=postgresql://auditmaster:auditmaster@localhost:5432/auditmaster
uvicorn app.main:app --reload --port 8000
```

Web:

```bash
cd apps/web
npm ci
npm run dev
```

Open http://localhost:3000. The shell is in Turkish: Denetimler, RCM Oluşturucu, Test Planları, Veri Analizi, and Doküman Kütüphanesi. Light and dark mode are in the header.

## Checks

```bash
cd apps/web && npm ci && npm run lint && npm run typecheck && npm run build
cd services/api && pip install -e ".[dev]" && ruff check . && pytest
```

GitHub Actions runs the same web build and API tests on pull requests.

## API surface in this scaffold

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Process is up. Reports the configured LLM base URL and model. Does not call the model and does not return the API key. |
| `GET` | `/ready` | Postgres accepts connections and the `vector` extension is installed. |

`app.llm.LLMClient` is the only LLM entry point. It is not used by a route yet.

## Suggested next steps

1. Document ingestion into pgvector: chunking, embeddings through the same OpenAI-compatible endpoint, and citation metadata.
2. RCM generation that returns risks, controls, and tests with source passages. Synthetic documents only until real reports are approved for use.
3. Test-plan recommendations per risk and control, still marked as recommendations.
4. Excel/CSV upload and a DuckDB/pandas check for duplicate payments, with the query and source file shown beside the result.
5. Authentication and an audit trail of what the model proposed and what the auditor accepted.
