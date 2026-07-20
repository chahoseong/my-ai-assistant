# Backend

FastAPI backend for the multi-turn assistant. Conversations and messages are
stored in PostgreSQL, and assistant text is delivered as an SSE stream.

## Prerequisites

- Python 3.14
- `uv`
- Docker Desktop with Compose
- `llama-server` and a compatible GGUF model

The default model configuration is:

```text
LLAMA_MODEL=google/gemma-4-E4B-it-qat-q4_0-gguf
LLAMA_BASE_URL=http://127.0.0.1:8080/v1
LLAMA_API_KEY=llama.cpp
```

## Install

Run commands from this directory:

```powershell
uv sync
```

`.env.example` documents the local URLs, but this project does not load a
`.env` file automatically. Set the variables explicitly in each PowerShell
session.

## Database runbook

### 1. Start PostgreSQL and check health

```powershell
docker compose up -d postgres
docker compose ps
docker compose exec postgres pg_isready -U assistant -d assistant_dev
```

The Compose initialization script creates both databases:

```text
assistant_dev   development database
assistant_test  test database
```

Do not run `docker compose down -v` against a database containing data. The
`-v` option removes the named PostgreSQL volume.

### 2. Set separated URLs

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://assistant:assistant@127.0.0.1:5432/assistant_dev"
$env:TEST_DATABASE_URL = "postgresql+asyncpg://assistant:assistant@127.0.0.1:5432/assistant_test"
```

The two URLs must refer to different databases. The test suite fails before
connecting if `TEST_DATABASE_URL` is missing or exactly equal to
`DATABASE_URL`.

### 3. Apply the development schema

With `DATABASE_URL` pointing to `assistant_dev`:

```powershell
uv run alembic upgrade head
uv run alembic current
```

Tests apply the same migration to `assistant_test` in the protected test
fixture. Never point `DATABASE_URL` at a service or production database.

## Run tests and quality checks

Keep the separated URLs set, then run:

```powershell
uv run pytest
uv run ruff format --check app tests
uv run ruff check app tests
uv run pyright app tests
```

Tests use the real PostgreSQL test database and truncate test tables before and
after each test. They never use the development database.

## Authentication configuration

Authentication uses a server-stored session cookie. Set these variables before
starting FastAPI:

```powershell
$env:APP_ENV = "local"
$env:SESSION_COOKIE_SECURE = "false"
$env:AUTH_ALLOWED_ORIGINS = "http://127.0.0.1:5173"
```

`SESSION_COOKIE_SECURE` accepts only `true` or `false`. It must be `true` when
`APP_ENV` is not `local`; FastAPI refuses to start otherwise. The local HTTP
setting above allows only the Vite development origin and is only for local
development.

Sessions are fixed at 30 days. The cookie is httpOnly, host-only, `Path=/`, and
`SameSite=Lax`; the database stores only the SHA-256 hash of its random token.
Unsafe requests with an `Origin` header must exactly match
`AUTH_ALLOWED_ORIGINS`; `Origin: null` is rejected. JSON body endpoints also
require `Content-Type: application/json`. Header-less curl requests remain
available for local verification.

## Destructive authentication migration

Revision `20260718_0003` deletes all existing conversations and messages before
making `conversations.user_id` mandatory. It is intended only for this
pre-production project state.

1. Stop FastAPI and confirm `DATABASE_URL` points to the intended development
   database, never a production database.
2. Run `uv run alembic upgrade head`.
3. Do not rely on downgrade to recover deleted conversations: downgrade restores
   only the nullable schema, not deleted data.

## Cookie authentication walkthrough

Use a cookie jar for a local API smoke test:

```powershell
curl.exe -i -c cookies.txt -H "Content-Type: application/json" -d '{"username":"alice","password":"correct horse battery staple"}' http://127.0.0.1:8001/api/auth/signup
curl.exe -i -c cookies.txt -H "Content-Type: application/json" -d '{"username":"alice","password":"correct horse battery staple"}' http://127.0.0.1:8001/api/auth/login
curl.exe -i -b cookies.txt http://127.0.0.1:8001/api/auth/me
curl.exe -i -b cookies.txt -H "Content-Type: application/json" -d '{"title":"First conversation"}' http://127.0.0.1:8001/api/conversations
curl.exe -i -b cookies.txt -X POST http://127.0.0.1:8001/api/auth/logout
```

For browser-originated unsafe requests, include an allowed `Origin` header.

## Run the services

### llama-server

In a separate terminal, start the OpenAI-compatible local model server:

```powershell
llama-server -m "path\to\gemma-4-E4B_q4_0-it.gguf" --port 8080
```

Override `LLAMA_MODEL`, `LLAMA_BASE_URL`, or `LLAMA_API_KEY` before starting
FastAPI when using a different model server.

### FastAPI

In the backend directory, with `DATABASE_URL` pointing to `assistant_dev`.
On Windows, set UTF-8 output so the FastAPI CLI can render its startup
messages in a `cp949` PowerShell console:

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
uv run fastapi dev app/main.py --host 127.0.0.1 --port 8001
```

### React frontend

In another terminal, run the Vite app from `frontend/`:

```powershell
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` to FastAPI, so the browser
uses the server-owned httpOnly session cookie without storing credentials in
JavaScript or browser storage.

Use this exact `127.0.0.1` address, not `http://localhost:5173`. The local
Origin allowlist intentionally accepts only `http://127.0.0.1:5173`.

After startup, verify that the current application is loaded before sending
requests:

```powershell
$openapi = Invoke-RestMethod -Uri "http://127.0.0.1:8001/openapi.json"
$openapi.paths.PSObject.Properties.Name | Sort-Object
```

The output must include `/api/conversations` and
`/api/conversations/{conversation_id}/messages`.

### Prometheus

`/metrics` is unauthenticated so Prometheus can collect it. This is a local
development setup only: production deployment must restrict access to that
endpoint.

With FastAPI running on `127.0.0.1:8001`, start Prometheus separately from the
PostgreSQL Compose stack:

```powershell
docker compose -f compose.observability.yaml up -d
docker compose -f compose.observability.yaml ps
```

Open `http://127.0.0.1:9090/targets` and confirm the `my-ai-assistant` target
is `UP`. Prometheus scrapes `host.docker.internal:8001` every 15 seconds; this
host name lets the container reach the FastAPI process running on the host.
Query `http_requests_total` in the Prometheus UI to inspect the collected time
series.

The UI listens only on `127.0.0.1:9090`. Prometheus data persists in the
`prometheus_data` named volume. `docker compose -f compose.observability.yaml
down` keeps it, while adding `-v` removes the stored time series.

### Metrics reference

Prometheus stores the measurements, while its query screen asks a question of
those measurements. Enter a query below at `http://127.0.0.1:9090/query` and
select **Execute**. After generating a request, wait up to 15 seconds for the
next scrape before querying.

Counters restart when the FastAPI process restarts. Use `rate` or `increase`
for a change over time; use a raw counter value only when inspecting the
current process lifetime.

| Metric | Type and labels | What it answers |
| --- | --- | --- |
| `http_requests_total` | Counter: `method`, `path`, `status` | How many requests reached each route and what status they returned. `path` is a route template, never a conversation ID or raw URL. Unknown HTTP methods are grouped as `OTHER`. |
| `http_request_duration_seconds` | Histogram: `method`, `path` | How long each HTTP request took. Prometheus exposes `_bucket`, `_count`, and `_sum` series for a histogram. |
| `llm_first_token_seconds` | Histogram | How long it took from starting an LLM call until its first streamed token. |
| `llm_stream_duration_seconds` | Histogram | How long completed LLM streams took in total. |
| `llm_stream_deltas_total` | Counter | How many streamed text chunks the LLM emitted. |
| `llm_stream_failures_total` | Counter | How many LLM streams failed after they began. A cancelled client request is not counted as a failure. |
| `conversation_lock_conflicts_total` | Counter | How often a second request tried to stream into a conversation already being streamed. These requests return `409 Conflict`. |
| `db_pool_in_use` | Gauge | How many SQLAlchemy database connections are currently checked out from the pool. |

#### Useful PromQL queries

```promql
# Requests grouped by route, method, and response status.
sum by (method, path, status) (http_requests_total)

# Request rate over the past five minutes.
sum by (method, path, status) (rate(http_requests_total[5m]))

# p95 HTTP latency by route. Histograms require their _bucket series.
histogram_quantile(
  0.95,
  sum by (le, method, path) (rate(http_request_duration_seconds_bucket[5m]))
)

# LLM stream failures during the past five minutes.
increase(llm_stream_failures_total[5m])

# p95 time to the first LLM token.
histogram_quantile(
  0.95,
  sum by (le) (rate(llm_first_token_seconds_bucket[5m]))
)

# p95 total LLM stream duration.
histogram_quantile(
  0.95,
  sum by (le) (rate(llm_stream_duration_seconds_bucket[5m]))
)

# Current number of database connections in use.
db_pool_in_use
```

`/metrics` itself is intentionally excluded from `http_requests_total` and
`http_request_duration_seconds`. Otherwise, every Prometheus scrape would
create another application request measurement and distort the data it is
collecting.

## Multi-turn API walkthrough

### Create a conversation

```powershell
$conversation = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8001/api/conversations" `
  -ContentType "application/json" `
  -Body '{}'

$conversationId = $conversation.id
```

### Send a message over SSE

Use `curl.exe -N` so PowerShell does not buffer the stream. Set UTF-8 output
when sending non-ASCII text.

```powershell
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

'{"message":"첫 번째 질문"}' |
  curl.exe -N -X POST "http://127.0.0.1:8001/api/conversations/$conversationId/messages" `
    -H 'Content-Type: application/json' `
    --data-binary '@-'
```

The response contains `data` events for text deltas and an `event: done` only
after the assistant message has been committed to PostgreSQL.

Send a second message using the same conversation ID to verify that previous
messages are loaded as model history:

```powershell
'{"message":"이전 내용을 바탕으로 요약해줘"}' |
  curl.exe -N -X POST "http://127.0.0.1:8001/api/conversations/$conversationId/messages" `
    -H 'Content-Type: application/json' `
    --data-binary '@-'
```

### Read persisted messages

```powershell
Invoke-RestMethod `
  -Method Get `
  -Uri "http://127.0.0.1:8001/api/conversations/$conversationId/messages"
```

Messages are returned in `created_at ASC, id ASC` order. A missing conversation
returns `404`; an existing conversation with no messages returns `200` and
`[]`.

## Failure and concurrency checks

- Stop `llama-server` while FastAPI is running and send a message. The SSE
  response contains `event: error`; no assistant `done` event is sent.
- Start two requests for the same conversation at once. The second request
  returns `409 Conflict` without storing a second user message.
- Requests for different conversations can stream concurrently.
- If the client disconnects, the in-process conversation lock is released in
  `finally`, allowing a later request to continue.

## Persistence after restart

Stop and restart only the FastAPI process, leaving PostgreSQL running:

```powershell
# Stop the FastAPI terminal with Ctrl+C, then run again:
uv run fastapi dev app/main.py
```

Call the message-list endpoint again with the same conversation ID. The rows
remain because they are stored in PostgreSQL, not in process memory.

## Official references

- Docker Compose: https://docs.docker.com/compose/
- Alembic tutorial: https://alembic.sqlalchemy.org/en/latest/tutorial.html
- FastAPI responses: https://fastapi.tiangolo.com/advanced/custom-response/
- Pydantic AI message history:
  https://pydantic.dev/docs/ai/core-concepts/message-history/
