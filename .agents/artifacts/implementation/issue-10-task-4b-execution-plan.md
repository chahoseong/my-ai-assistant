# Issue #10 Task 4b: LLM Failure and Cancellation Observability

**Goal:** Count actual LLM stream failures and emit the existing failure event as correlated stdout JSON, while excluding client cancellation from the failure counter.

## Scope

- Add `record_llm_stream_failure()` in `app.observability`.
- In `stream_persisted_message`, keep the LLM stream and database persistence in separate exception boundaries. Re-raise `asyncio.CancelledError` without recording failure; increment the counter only for an LLM-boundary exception, while both boundaries emit `message_stream_failed` through structlog as stdout JSON.
- Extend the existing failure and cancellation tests with metric and request-ID correlation assertions.
- Do not change successful-stream metrics, SSE error/done payloads, persistence, or lease-release behavior.

## Acceptance criteria

- A `FailingAgent` stream increments `llm_stream_failures_total` by exactly 1 and emits one JSON `message_stream_failed` event correlated to its JSON access log by `request_id`.
- Cancelling an active stream leaves `llm_stream_failures_total` unchanged and still releases the conversation lease.
- The existing SSE `error` response for LLM failure and cancellation propagation behavior remain unchanged.

## Test-first execution

1. Add counter and JSON correlation assertions to the existing failing-stream test, and a no-increment assertion to the existing cancelled-stream test.
2. Confirm RED because neither helper nor structlog migration exists in `chat.py`.
3. Add the helper and minimal exception-branch changes.
4. Run failure, cancellation, streaming, and observability regressions.

## Verification

```powershell
uv run pytest tests/test_message_failures.py tests/test_message_concurrency.py tests/test_message_streaming.py tests/test_observability.py -q
uv run ruff format --check app/observability.py app/routers/chat.py tests/test_message_failures.py tests/test_message_concurrency.py
uv run ruff check app/observability.py app/routers/chat.py tests/test_message_failures.py tests/test_message_concurrency.py
uv run pyright app/observability.py app/routers/chat.py tests/test_message_failures.py tests/test_message_concurrency.py
uv run pytest -q
```

## References

- structlog contextvars: https://www.structlog.org/en/stable/contextvars.html
- Prometheus Python counters: https://prometheus.github.io/client_python/instrumenting/counter/
