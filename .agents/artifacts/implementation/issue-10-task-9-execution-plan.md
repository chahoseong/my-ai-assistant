# Issue #10 Task 9: Independent Review Remediation

**Goal:** Apply the two validated findings from the independent review without changing API behavior.

## Scope

- Prevent exception messages and tracebacks from being rendered in application JSON logs; keep stable event names and request correlation.
- Bound the HTTP method Prometheus label to known methods plus `OTHER`.
- Add regression tests for both boundaries.

## Acceptance criteria

- [ ] A stream failure whose exception contains a unique secret does not emit that secret to stdout logs.
- [ ] Unknown HTTP methods increment only the `OTHER` metric label, while request routing/status semantics remain unchanged.
- [ ] Existing request correlation and metric behavior remain covered by the test suite.

## Verification

```powershell
uv run pytest tests/test_message_failures.py::test_llm_failure_keeps_user_only_and_sends_error_event tests/test_observability.py::test_unknown_http_methods_share_fixed_metric_label -q
uv run ruff format --check app tests
uv run ruff check app tests
uv run pyright app tests
uv run pytest -q
```

## Dependencies

Task 8. This is a small, focused follow-up to the independent review.

## Files likely touched

- `backend/app/observability.py`
- `backend/app/routers/auth.py`
- `backend/app/routers/chat.py`
- `backend/app/routers/conversations.py`
- `backend/app/routers/messages.py`
- `backend/tests/test_message_failures.py`
- `backend/tests/test_observability.py`

## References

- Structlog exception rendering: https://www.structlog.org/en/stable/exceptions.html
- Prometheus metric and label guidance: https://prometheus.io/docs/practices/instrumentation/
