# Issue #10 Task 6: Expose Metrics without Self-Observation

**Goal:** Make the existing Prometheus metrics available at unauthenticated `/metrics`, while keeping scrape traffic out of application HTTP metrics.

## Decisions

- Mount Prometheus client's purpose-built ASGI application with `make_asgi_app()` instead of reimplementing the exposition response as a FastAPI route.
- Bypass `RequestObservabilityMiddleware` for the fixed `/metrics` path, so periodic scraper requests do not add `path="/metrics"` time series or distort API rate and duration metrics.
- Keep `/metrics` unauthenticated as Issue #10 specifies; the README will document its local-only access boundary in the infrastructure/documentation task.

## Acceptance criteria

- `GET /metrics` returns HTTP 200 without authentication and contains `http_requests_total`.
- Scraping `/metrics` does not create an `http_requests_total{path="/metrics", ...}` series.
- Non-metrics HTTP behavior remains unchanged.

## Test-first execution

1. Add an endpoint test for the response status, Prometheus text, and no `/metrics` HTTP-metric label.
2. Confirm it is RED because the application has no mount.
3. Mount `make_asgi_app()` at `/metrics` and add the middleware bypass for that fixed path.
4. Run observability tests, static checks, and the full suite.

## Files

- `backend/app/main.py`
- `backend/app/observability.py`
- `backend/tests/test_observability.py`

## References

- Prometheus ASGI exporter: https://prometheus.github.io/client_python/exporting/http/asgi/
- Prometheus FastAPI mounting example: https://prometheus.github.io/client_python/exporting/http/fastapi-gunicorn/
- FastAPI sub-application mounts: https://fastapi.tiangolo.com/advanced/sub-applications/
