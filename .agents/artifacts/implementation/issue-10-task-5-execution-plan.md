# Issue #10 Task 5: Lock Conflict and Database Pool Observability

**Goal:** Record rejected concurrent conversation requests and expose the database pool's current checked-out connection count.

## Scope

- Add a small helper that increments `conversation_lock_conflicts_total`.
- Call it only in the chat route's existing 409 conflict branch.
- Bind `db_pool_in_use` to the SQLAlchemy pool's `checkedout()` function when a database engine is created.
- Extend concurrency and database/observability tests.
- Do not add metric labels, alter locking behaviour, or update the gauge on request paths.

## Acceptance criteria

- A same-conversation request rejected with HTTP 409 increases `conversation_lock_conflicts_total` by exactly one.
- `db_pool_in_use` reads the latest value from its registered callback at collection time.
- Each newly created `Database` registers its own engine pool's `checkedout()` callback.

## Test-first execution

1. Add a counter delta assertion to the existing concurrent-message test.
2. Add a small gauge callback test and a database construction test that proves the pool callback is registered.
3. Confirm the focused tests are RED because the helpers and registration do not exist.
4. Add the minimal observability helpers, invoke the counter at the existing 409 boundary, and register the callback in `create_database`.
5. Run focused tests, static checks, and the whole test suite.

## Why callback registration

`Gauge.set_function` evaluates its function whenever Prometheus collects metrics. A connection pool is therefore measured from its authoritative current state, avoiding a stale counter when exceptions or cancellations skip a matching decrement.

## Verification

```powershell
uv run pytest tests/test_message_concurrency.py tests/test_db.py tests/test_observability.py -q
uv run ruff format --check app/observability.py app/db.py app/routers/chat.py tests/test_message_concurrency.py tests/test_db.py tests/test_observability.py
uv run ruff check app/observability.py app/db.py app/routers/chat.py tests/test_message_concurrency.py tests/test_db.py tests/test_observability.py
uv run pyright app/observability.py app/db.py app/routers/chat.py tests/test_message_concurrency.py tests/test_db.py tests/test_observability.py
uv run pytest -q
```

## References

- Prometheus Python Gauge callbacks: https://prometheus.github.io/client_python/instrumenting/gauge/
- SQLAlchemy pooling: https://docs.sqlalchemy.org/en/20/core/pooling.html
