# AuditMaster

Working space for an enterprise internal audit team. The auditor always makes the final decision. Every AI suggestion is shown with the passages it used. A suggestion with no usable citation is marked **Kaynaksız**.

This repository now runs the first end-to-end flow: a document library, hybrid retrieval, and a risk control matrix (RCM) the auditor can accept, edit, reject, and save.

## What you can do

1. Upload PDF, DOCX, TXT, or Markdown into **Doküman Kütüphanesi**, tagged by type (geçmiş denetim raporu, bulgu, prosedür, standart, iyi uygulama) and optionally by audit area (for example Satın Alma).
2. The API extracts text, chunks it with document, page, and section metadata, embeds the chunks, and stores them in Postgres with pgvector.
3. On **RCM Oluşturucu**, enter a scope such as `Satın alma denetimi`. The API retrieves relevant chunks and asks the model for risks, controls, and tests as JSON. Each item carries citations. Invalid JSON is repaired once, then rejected.
4. Review the matrix, open a citation to read the snippet, decide on each row, and save the RCM against an audit. Export to Excel when you want a workbook.

Test plans and spreadsheet analysis are still placeholders.

Three tiny fixtures live in `services/api/tests/fixtures/`. They are labelled örnek / test fikstürü and are not a synthetic corpus. Upload them yourself when you want a demo; the database starts empty.

- `ornek-satin-alma-proseduru.md` — prosedür, Satın Alma
- `ornek-satin-alma-bulgusu.txt` — bulgu, Satın Alma
- `ornek-satin-alma-standardi.md` — standart, Satın Alma

## Architecture

```
apps/web          Next.js App Router, TypeScript, Tailwind, shadcn/ui
services/api      FastAPI. Parsing, retrieval, and RCM generation
Postgres          pgvector, documents, chunks, audits, saved RCMs
```

The browser talks to the API over HTTP. Python owns parsing and retrieval so those libraries stay off the Node side.

### Cloud now, on-prem later

Every new dependency can be self-hosted. Nothing calls a proprietary cloud-only API.

- Next.js and FastAPI are ordinary containers.
- Postgres with pgvector is a standard image.
- Chat and embeddings go through an OpenAI-compatible HTTP API (`OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`, and the embedding variables below). The same client points at a hosted open-weight server now and at vLLM or Ollama later.
- Parsing uses pypdf and python-docx. They ship no model weights. Docling is the better parser for scanned pages and complex layout, but it downloads weights and pulls in PyTorch, so it is not in the default image. `parse_document` in `services/api/app/parsing.py` is the seam: a Docling backend should still return blocks with page and section metadata.
- Optional local embeddings use `sentence-transformers` (`pip install "auditmaster-api[local]"`). Leave that extra off unless you want the weights inside the API process.
- The optional reranker is a self-hosted HTTP hook, matching Hugging Face Text Embeddings Inference `POST /rerank`.

## Run locally

Requirements: Docker with Compose, or Node.js 22 and Python 3.12 if you run the processes yourself.

### Docker Compose

Compose defaults to **fake models**, so the flow runs with no API key:

```bash
cp .env.example .env   # optional; compose has the same local defaults
docker compose up --build
```

- Web: http://localhost:3000
- API health: http://localhost:8000/health (`llm.mode` is `fake` until you turn fake mode off)
- API readiness (Postgres and pgvector): http://localhost:8000/ready
- Postgres: `localhost:5432`, database `auditmaster`, user `auditmaster`

Then upload one of the fixtures, open **RCM Oluşturucu**, enter `Satın alma denetimi`, and generate. The header badge **Deterministik örnek model** means the API did not call a model server.

The password in `.env.example` is a local default. Change it before using the stack anywhere else. Do not commit `.env`.

`NEXT_PUBLIC_API_URL` is read when the web image is built, because the browser calls the API directly. The default `http://localhost:8000` matches the published API port.

Postgres starts empty. `docker compose down -v` drops the volume if you need a clean library.

### Without Docker

Start Postgres 16 with pgvector yourself and run `infra/postgres/init.sql`, or start only the database:

```bash
docker compose up db
```

The API creates its tables on the first request that needs them (`CREATE EXTENSION vector` plus the document, chunk, audit, and RCM tables).

API:

```bash
cd services/api
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
export FAKE_MODELS=true
export DATABASE_URL=postgresql://auditmaster:auditmaster@localhost:5432/auditmaster
uvicorn app.main:app --reload --port 8000
```

Web:

```bash
cd apps/web
npm ci
npm run dev
```

Open http://localhost:3000. The shell is in Turkish. Light and dark mode are in the header.

## Point the API at a real model

Set `FAKE_MODELS=false`. Chat and embeddings stay OpenAI-compatible; only the base URL, model name, and key change.

The embedding column is `vector(1024)`. Use a model that returns 1024 dimensions. **BAAI/bge-m3** is the intended multilingual model (Turkish included) and can run locally. If the server returns another size, ingestion fails with an explicit error instead of writing a bad vector.

From the API container, `localhost` is the container, not the host. A model server on the same machine must be reached by a host address (for example `http://172.17.0.1:11434/v1` on Linux, or `http://host.docker.internal:11434/v1` on Docker Desktop). If you run the API on the host (`docker compose up db` only), `localhost` is correct.

### Hosted open-weight server now

Any server that implements `POST /v1/chat/completions` and `POST /v1/embeddings` works. Example: vLLM or a similar gateway on a GPU box you control.

```bash
FAKE_MODELS=false
OPENAI_BASE_URL=https://llm.example.internal/v1
OPENAI_API_KEY=replace-me
OPENAI_MODEL=Qwen/Qwen2.5-32B-Instruct

EMBEDDING_MODE=openai
EMBEDDING_BASE_URL=https://embed.example.internal/v1
EMBEDDING_API_KEY=replace-me
EMBEDDING_MODEL=BAAI/bge-m3
```

Leave `EMBEDDING_BASE_URL` empty to use `OPENAI_BASE_URL` for both. Ollama can serve both on one URL with different model names.

Rebuild the web image only if `NEXT_PUBLIC_API_URL` changes. The model settings are read by the API at startup.

### vLLM and TEI on-prem later

```bash
FAKE_MODELS=false
OPENAI_BASE_URL=http://vllm:8000/v1
OPENAI_API_KEY=local-dev
OPENAI_MODEL=Qwen/Qwen2.5-32B-Instruct

EMBEDDING_BASE_URL=http://tei:80/v1
EMBEDDING_MODEL=BAAI/bge-m3
```

`OPENAI_API_KEY` can be a placeholder when the server does not check it. The client never logs the key, and `/health` only reports whether a key is set.

To embed inside the API process instead of calling HTTP:

```bash
pip install "auditmaster-api[local]"
EMBEDDING_MODE=local
EMBEDDING_MODEL=BAAI/bge-m3
```

The first call downloads the weights unless you have already placed them on disk for sentence-transformers. That download is why local mode is not the default image.

### Optional reranker

```bash
RERANKER_URL=http://tei-rerank:80/rerank
```

The API posts `{"query": "...", "texts": ["...", "..."]}` and expects `[{"index": 0, "score": 0.9}]` (a `{"results": [...]}` wrapper is also accepted). If the call fails, hybrid order is kept.

## Retrieval and Turkish

Search is hybrid:

- pgvector cosine similarity on the 1024-d embedding
- Postgres full text, fused with reciprocal rank fusion

Full-text rank is `ts_rank_cd`. It uses term frequency and a length normalization, so it is BM25-style. It is not Okapi BM25. Postgres does not ship Okapi BM25; a self-hosted BM25 extension can replace the lexical query later.

Turkish text uses the `turkish` snowball configuration when the server has it (Postgres 16 does). That stemmer is light and misses many agglutinative suffixes (`alımlar` will not always meet `alım`). A second `simple` tsvector is stored from a folded copy of the text: `ç→c`, `ğ→g`, `ı/İ/I→i`, `ö→o`, `ş→s`, `ü→u`. An ASCII query such as `satin alma` can therefore match `satın alma`. Folding cannot tell `ı` and `i` apart, and the database locale does not implement Turkish casing, which is why the fold happens in the application rather than with `unaccent` or `lower()`.

Fake embeddings are a deterministic hash of those folded tokens. They are not semantic. Shared keywords sit near each other so the demo and the tests can retrieve without a model. `/health` reports `embedding_mode: fake` in that mode and still shows the configured model name (`BAAI/bge-m3` by default) so you can see what a real deployment would call.

## Checks

```bash
cd apps/web && npm ci && npm run lint && npm run typecheck && npm run build
cd services/api && pip install -e ".[dev]" && ruff check . && pytest
```

API tests that talk to Postgres skip unless `DATABASE_URL` is set. CI sets `DATABASE_URL` and `REQUIRE_DATABASE=1` against `pgvector/pgvector:pg16`, so a missing database fails the job. Parsing, RCM schema validation, citation flagging, fake embeddings, and rank fusion run without Postgres.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Process is up. Reports the LLM and embedding mode. Does not call the model and does not return the API key. |
| `GET` | `/ready` | Postgres accepts connections and the `vector` extension is installed. |
| `POST` | `/documents` | Multipart upload: `file`, `doc_type`, optional `audit_area`. |
| `GET` | `/documents` | List documents. |
| `GET` | `/documents/{id}` | Document plus chunks (no embeddings). |
| `DELETE` | `/documents/{id}` | Delete the document and its chunks. |
| `POST` | `/retrieval/search` | Hybrid search. Body: `query`, optional `audit_area`, `limit`. |
| `POST` | `/rcm/generate` | Retrieve and draft an RCM. Does not save. |
| `GET` | `/audits` | Audits and whether an RCM is saved. |
| `GET` | `/audits/{id}` | Audit plus its current RCM. |
| `POST` | `/rcms` | Create or update the audit's RCM, including row decisions. |
| `GET` | `/rcms/{id}` | Saved RCM. |
| `GET` | `/rcms/{id}/export` | Excel workbook. |

`app.llm.LLMClient` is the only chat and embeddings entry point.

## Suggested next steps

1. Test-plan recommendations per accepted risk and control, still marked as recommendations.
2. Excel/CSV upload and a DuckDB/pandas check for duplicate payments, with the query and source file shown beside the result.
3. Authentication and an audit trail of what the model proposed and what the auditor accepted.
4. A Docling parser behind `parse_document` for scanned PDFs, kept optional so the default image stays small.
