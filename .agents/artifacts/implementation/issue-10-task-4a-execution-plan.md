# Issue #10 Task 4a: Successful SSE Stream Metrics

**Goal:** Record TTFT, successful LLM stream duration, and delta count without changing SSE events or persistence behavior.

## Scope

- Add small recording helpers in `app.observability` for the three existing LLM metrics.
- In `stream_persisted_message`, start timing immediately before `run_stream`, record TTFT only on the first delta, increment the delta counter for every delta, and record duration immediately after the stream iterator ends normally.
- Extend the existing successful streaming integration test with metric sample-count and counter-delta assertions.
- Do not migrate `message_stream_failed`, increment the failure counter, or change cancellation handling in this increment.

## Acceptance criteria

- One successful two-delta stream increases `llm_first_token_seconds_count` by 1, `llm_stream_duration_seconds_count` by 1, and `llm_stream_deltas_total` by 2.
- The duration observation ends before database persistence and SSE `done` emission.
- Existing SSE deltas, `done`, stored assistant message, and lease behavior remain unchanged.

## Test-first execution

1. Add the three metric-increment assertions to the successful two-delta stream test.
2. Run it to confirm RED because no LLM metric is currently recorded.
3. Add observability helpers and the minimal stream-loop calls.
4. Run the successful-stream test and then the streaming regression suite.

## Verification

```powershell
uv run pytest tests/test_message_streaming.py tests/test_observability.py -q
uv run ruff format --check app/observability.py app/routers/chat.py tests/test_message_streaming.py
uv run ruff check app/observability.py app/routers/chat.py tests/test_message_streaming.py
uv run pyright app/observability.py app/routers/chat.py tests/test_message_streaming.py
uv run pytest -q
```

## References

- Prometheus Python metric types: https://prometheus.github.io/client_python/instrumenting/
