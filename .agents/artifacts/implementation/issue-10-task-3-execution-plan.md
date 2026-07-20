# Issue #10 Task 3: Structured Router Failure Logs

**Goal:** Migrate existing non-streaming router failure events to structlog while preserving event names, HTTP behavior, and request-level correlation.

## Scope

- Replace standard-library logger declarations in `auth.py`, `conversations.py`, and `messages.py` with `app.observability.get_logger`.
- Preserve all existing event names while recording exception details with `logger.error("event_name", exc_info=True)` so JSON output remains on stdout.
- Add a request-level controlled database failure that asserts `signup_failed` and `http_request_complete` are JSON logs with the same `request_id`.
- Do not modify the chat/SSE router, add metrics, add labels, or log request data.

## Test-first execution

1. Add the controlled-signup-failure correlation integration test in `backend/tests/test_observability.py`.
2. Run it to confirm RED: the existing standard-library router log is not the required structlog JSON event.
3. Migrate the three router logger declarations to `get_logger(__name__)`.
4. Run the targeted test set and verify existing error status/body behavior is unchanged.
5. Run Ruff, Pyright, full backend tests, review the staged diff, and commit.

## Acceptance criteria

- `signup_integrity_error`, `signup_failed`, `login_session_create_failed`, `conversation_list_failed`, `conversation_create_failed`, and `message_list_failed` remain unchanged.
- A request whose `AsyncSession.commit()` raises `SQLAlchemyError` returns its existing 500 response and yields exactly one `signup_failed` JSON log plus one `http_request_complete` JSON log with the same parseable UUID `request_id`.
- Router calls pass no payload, headers, cookies, token, password, user ID, or exception text as explicit structured fields.

## Verification

```powershell
uv run pytest tests/test_observability.py tests/test_auth_signup.py tests/test_auth_login.py tests/test_conversations.py tests/test_messages.py -q
uv run ruff format --check app/routers/auth.py app/routers/conversations.py app/routers/messages.py tests/test_observability.py
uv run ruff check app/routers/auth.py app/routers/conversations.py app/routers/messages.py tests/test_observability.py
uv run pyright app/routers/auth.py app/routers/conversations.py app/routers/messages.py tests/test_observability.py
uv run pytest -q
```

## References

- structlog contextvars: https://www.structlog.org/en/stable/contextvars.html
- structlog bound logger error method: https://www.structlog.org/en/stable/api.html#structlog.stdlib.BoundLogger.error
