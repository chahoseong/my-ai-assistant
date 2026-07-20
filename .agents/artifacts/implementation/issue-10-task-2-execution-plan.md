# Issue #10 Task 2: HTTP Request Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Execute inline with test-first cycles; do not add LLM, DB-pool, Prometheus endpoint, or router event-log behavior in this increment.

**Goal:** Instrument every HTTP request with one JSON access log, a UUID `request_id`, bounded route-template labels, and the two HTTP Prometheus metrics.

**Architecture:** Add a stateless pure-ASGI `RequestObservabilityMiddleware` and small `app.observability` helpers. The middleware binds request context before calling the inner application, observes `http.response.start` through a wrapped `send`, and records one result in `finally` after the application has completed. A matched route uses `scope["route"].path`; unmatched requests use the fixed `__unmatched__` label.

**Tech Stack:** FastAPI `>=0.130,<0.140`, Starlette pure ASGI middleware, structlog `26.1.x`, prometheus-client `0.25.0`, pytest, Ruff, Pyright.

## Global Constraints

- Use the existing `app.observability` module as the sole metrics/logging boundary.
- `path` metric labels must never use `scope["path"]` or a UUID-bearing URL.
- Access logs contain exactly `method`, `path`, `status`, `duration_ms`, and `request_id` plus a stable event name.
- Do not log request bodies, headers, cookies, passwords, or tokens.
- Do not add `/metrics`, LLM metrics, DB-pool binding, Compose, or router event migration in this increment.

---

### Task 1: Request lifecycle contract tests

**Files:**

- Modify: `backend/tests/test_observability.py`
- Modify: `backend/tests/test_main.py`

**Interfaces:**

- Consumes: `app.main.app`, `HTTP_REQUESTS_TOTAL`, and `HTTP_REQUEST_DURATION_SECONDS`.
- Produces failing integration tests for one access log per request, stable request ID, counter/histogram increments, matched route templates, and `__unmatched__` fallback.

- [x] **Step 1: Write a matched-route failing test.**

  Send an unauthenticated request to a UUID-bearing message URL. It must return 401, then assert the captured JSON access log has the route template `/api/conversations/{conversation_id}/messages`, a parseable UUID `request_id`, status 401, and non-negative `duration_ms`. Snapshot the matching HTTP counter and histogram samples before the request and assert their values increased afterward.

- [x] **Step 2: Run the matched-route test and verify RED.**

  Run:

  ```powershell
  uv run pytest tests/test_observability.py::test_message_request_uses_route_template_for_logs_and_metrics -q
  ```

  Expected: failure because the application has no request observability middleware or HTTP metric recording.

- [x] **Step 3: Write an unmatched-route failing test.**

  Send `GET /api/not-a-route`; assert the 404 access log and `http_requests_total` use `path="__unmatched__"`, not the actual path.

- [x] **Step 4: Run the unmatched-route test and verify RED.**

  Run:

  ```powershell
  uv run pytest tests/test_observability.py -q
  ```

  Expected: the new request-contract tests fail because the middleware has not been implemented.

### Task 2: Stateless pure-ASGI middleware and app integration

**Files:**

- Modify: `backend/app/observability.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/routers/auth.py`
- Modify: `backend/app/routers/conversations.py`
- Modify: `backend/app/routers/messages.py`
- Modify: `backend/app/routers/chat.py`
- Modify: `backend/tests/test_main.py`

**Interfaces:**

- Produces `RequestObservabilityMiddleware(app: ASGIApp)` with `async __call__(scope, receive, send) -> None`.
- Produces `record_http_request(method: str, path: str, status: int, duration_seconds: float) -> None`.
- Produces `route_template(scope: Scope) -> str`, returning an APIRoute template or `__unmatched__`.

- [x] **Step 5: Implement the minimum observability helpers.**

  Add `record_http_request` to increment `HTTP_REQUESTS_TOTAL` with `method`, template `path`, and decimal `status`, then observe `HTTP_REQUEST_DURATION_SECONDS` with `method` and template `path`. Add `route_template` that reads the matched route's `.path` and otherwise returns `__unmatched__`.

- [x] **Step 6: Implement the pure-ASGI middleware.**

  The `__call__` method must pass through non-HTTP scopes unchanged. For HTTP, clear and bind a fresh UUID request ID, start `perf_counter`, wrap `send` to retain `http.response.start` status, await the inner app, and in `finally` log `http_request_complete`, record the HTTP metrics, and clear contextvars. Default a missing status to 500 so unhandled exceptions are measured before being re-raised.

- [x] **Step 7: Install the middleware and retire the old text logger setup.**

  In `app.main`, call `configure_observability()` during application construction and register `RequestObservabilityMiddleware` through FastAPI's middleware API. Move each existing URL prefix from `app.include_router(..., prefix=...)` to its owning `APIRouter(prefix=...)`; this preserves public URLs while allowing the matched route template in the ASGI scope to include the full prefix. Remove the standard-library console logger setup and update/remove its old implementation-specific tests; the JSON contract is now asserted by `test_observability.py`.

- [x] **Step 8: Run the targeted tests and verify GREEN.**

  Run:

  ```powershell
  uv run pytest tests/test_observability.py tests/test_main.py -q
  ```

  Expected: all request-log, route-template, metric increment, and existing main tests pass.

### Task 3: Quality, regression, and commit

**Files:**

- Modify: `.agents/artifacts/implementation/issue-10-task-2-execution-plan.md`
- Modify only files listed in Tasks 1 and 2.

- [x] **Step 9: Run code-quality checks.**

  ```powershell
  uv run ruff format --check app/observability.py app/main.py app/routers tests/test_observability.py tests/test_main.py
  uv run ruff check app/observability.py app/main.py app/routers tests/test_observability.py tests/test_main.py
  uv run pyright app/observability.py app/main.py app/routers tests/test_observability.py tests/test_main.py
  ```

- [x] **Step 10: Run the full backend regression suite using the documented test database variables.**

  ```powershell
  $env:DATABASE_URL = "postgresql+asyncpg://assistant:assistant@127.0.0.1:5432/assistant_dev"
  $env:TEST_DATABASE_URL = "postgresql+asyncpg://assistant:assistant@127.0.0.1:5432/assistant_test"
  uv run pytest
  ```

  Expected: all existing and new tests pass.

- [ ] **Step 11: Commit the increment after staged-diff review.**

  ```powershell
  git add backend/app/observability.py backend/app/main.py backend/app/routers backend/tests/test_observability.py backend/tests/test_main.py .agents/artifacts/implementation/issue-10-task-2-execution-plan.md
  git diff --staged --check
  git diff --staged
  git commit -m "feat: instrument HTTP request lifecycle"
  ```

## Official References

- Pure ASGI middleware and typed `scope`, `receive`, `send`: https://www.starlette.io/middleware/#pure-asgi-middleware
- Inspecting response messages by wrapping `send`: https://www.starlette.io/middleware/#inspecting-or-modifying-the-response
- BaseHTTPMiddleware contextvars limitation: https://www.starlette.io/middleware/#limitations
- structlog contextvars: https://www.structlog.org/en/stable/contextvars.html

## Self-Review

- [x] The middleware holds only per-request local state; no request-specific state is stored on `self`.
- [x] The two tests prove bounded labels with a real UUID route and a real unmatched route.
- [x] The completion logic runs after the inner ASGI application and on exceptions.
- [x] No raw URL, request body, header, cookie, password, or token is emitted.
