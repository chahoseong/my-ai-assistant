# Issue #10 Task 1: Observability Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use inline execution with a test-first cycle. Each step is a checkbox and must be completed in order.

**Goal:** Add a single, centralized observability module that configures stdout JSON logs with structlog contextvars and declares only the eight Prometheus metrics required by Issue #10.

**Architecture:** `app.observability` is the only new production module in this increment. It exports a small configuration function, a structlog logger factory, and metric objects; no FastAPI middleware or router uses it yet. Later increments add the recording helpers. This keeps the increment reversible and lets tests define the logging and metric contracts before the request-lifecycle work begins.

**Tech Stack:** Python 3.14, structlog 26.1.x, prometheus-client, pytest, Ruff, Pyright.

## Global Constraints

- Use `structlog 26.1.x` and stdout JSON lines only.
- Do not log message bodies, passwords, session tokens, authorization values, or cookie values.
- Define only these metrics: `http_requests_total`, `http_request_duration_seconds`, `llm_first_token_seconds`, `llm_stream_duration_seconds`, `llm_stream_deltas_total`, `llm_stream_failures_total`, `conversation_lock_conflicts_total`, and `db_pool_in_use`.
- Keep metric labels exactly as specified by Issue #10; no identifiers or error text become labels.
- Do not alter routers, middleware, Compose, or README in this increment.

---

### Task 1: Define and implement the observability foundation

**Files:**

- Modify: `backend/pyproject.toml`
- Modify: `backend/uv.lock`
- Create: `backend/app/observability.py`
- Create: `backend/tests/test_observability.py`

**Interfaces:**

- Produces `configure_observability() -> None`: idempotently configures structlog to render JSON log records to stdout and merge contextvars.
- Produces `get_logger(name: str) -> structlog.stdlib.BoundLogger`: returns the logger used by later routers and middleware.
- Produces Prometheus metric objects with the Issue #10 names and required label sets. Later tasks call helper functions instead of importing Prometheus from routes.

- [ ] **Step 1: Add the two permitted runtime dependencies.**

  Update `backend/pyproject.toml` so the `dependencies` list contains entries compatible with:

  ```toml
  "prometheus-client>=0.23,<1",
  "structlog>=26.1,<26.2",
  ```

  Refresh `backend/uv.lock` with `uv lock`. This is configuration required to execute the failing test; it is not the observability implementation.

- [ ] **Step 2: Write the failing JSON/context contract test.**

  Create `backend/tests/test_observability.py` with a test that expresses the public behavior before `app.observability` exists:

  ```python
  import json

  import structlog

  from app.observability import configure_observability, get_logger


  def test_configured_logger_writes_json_with_bound_request_id(capsys) -> None:
      structlog.reset_defaults()
      configure_observability()
      structlog.contextvars.clear_contextvars()
      structlog.contextvars.bind_contextvars(request_id="request-123")

      get_logger("app.test").info("observability_probe")

      payload = json.loads(capsys.readouterr().out)
      assert payload["event"] == "observability_probe"
      assert payload["request_id"] == "request-123"
      assert payload["level"] == "info"
  ```

- [ ] **Step 3: Run the JSON/context test and verify RED.**

  Run:

  ```powershell
  uv run pytest tests/test_observability.py::test_configured_logger_writes_json_with_bound_request_id -q
  ```

  Expected: failure because `app.observability` does not exist. If the test fails for another reason, correct only the test setup and re-run until the missing module is the cause.

- [ ] **Step 4: Write the failing metric-contract test.**

  Extend `backend/tests/test_observability.py` to verify the module exposes metric objects whose public names and labels match the issue contract. The test must check all eight metric names and these labels:

  ```text
  http_requests_total: method, path, status
  http_request_duration_seconds: method, path
  llm_first_token_seconds: none
  llm_stream_duration_seconds: none
  llm_stream_deltas_total: none
  llm_stream_failures_total: none
  conversation_lock_conflicts_total: none
  db_pool_in_use: none
  ```

  Use each metric object's declared label names, not a request fixture, so this increment tests the metric schema only.

- [ ] **Step 5: Implement the smallest module that makes both contracts pass.**

  Create `backend/app/observability.py` with:

  ```python
  def configure_observability() -> None:
      structlog.configure(
          processors=[
              structlog.contextvars.merge_contextvars,
              structlog.processors.add_log_level,
              structlog.processors.format_exc_info,
              structlog.processors.JSONRenderer(),
          ],
          logger_factory=structlog.PrintLoggerFactory(),
          cache_logger_on_first_use=True,
      )


  def get_logger(name: str):
      return structlog.get_logger(name)
  ```

  Then declare one `Counter`, `Histogram`, or `Gauge` per required metric. Use `Counter` for totals, `Histogram` for durations, and `Gauge` for `db_pool_in_use`. Do not add a timestamp processor, middleware, endpoint, LLM helper, or DB callback yet; those belong to later planned tasks.

- [ ] **Step 6: Run the targeted tests and verify GREEN.**

  Run:

  ```powershell
  uv run pytest tests/test_observability.py -q
  ```

  Expected: all newly added tests pass. Confirm the JSON assertion exercises the real configured structlog logger rather than a mock.

- [ ] **Step 7: Verify this increment's quality checks.**

  Run:

  ```powershell
  uv run ruff format --check app/observability.py tests/test_observability.py
  uv run ruff check app/observability.py tests/test_observability.py
  uv run pyright app/observability.py tests/test_observability.py
  ```

  Expected: all commands exit with status 0.

- [ ] **Step 8: Review and commit the self-contained increment.**

  Inspect the staged diff for secrets and scope before committing:

  ```powershell
  git add backend/pyproject.toml backend/uv.lock backend/app/observability.py backend/tests/test_observability.py .agents/artifacts/implementation/issue-10-task-1-execution-plan.md
  git diff --staged
  git commit -m "feat: add observability foundation"
  ```

  The commit contains only dependencies, the observability foundation, its tests, and this execution plan.

## Official References

- structlog contextvars: https://www.structlog.org/en/stable/contextvars.html
- structlog configuration API: https://www.structlog.org/en/stable/api.html#structlog.configure
- Prometheus Python metric types: https://prometheus.github.io/client_python/instrumenting/
- Prometheus Gauge callback API: https://prometheus.github.io/client_python/instrumenting/gauge/#set_functionf

## Self-Review

- [ ] The plan covers no behavior beyond Task 1 of the approved Issue #10 plan.
- [ ] The only new runtime dependencies are the two explicitly allowed by the issue.
- [ ] Each production behavior is introduced after a failing test command.
- [ ] No placeholder, router change, middleware change, metric endpoint, or infrastructure change appears in this increment.
