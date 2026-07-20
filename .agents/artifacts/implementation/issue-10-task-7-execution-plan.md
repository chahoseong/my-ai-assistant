# Issue #10 Task 7: Run Prometheus Locally

**Goal:** Run a separate local Prometheus container that scrapes the host-run FastAPI metrics endpoint and provides its UI on localhost.

## Decisions

- Keep Prometheus in `compose.observability.yaml`, separate from the PostgreSQL Compose stack, because FastAPI itself runs on the host during local development.
- Pin the image to `prom/prometheus:v3.13.0` for reproducibility.
- Use `host.docker.internal:8001` as the static target; `localhost` inside a container would point to Prometheus itself.
- Scrape every `15s`, bind the UI to `127.0.0.1:9090`, mount configuration read-only, and persist time-series data in `prometheus_data`.

## Acceptance criteria

- `docker compose -f compose.observability.yaml config` validates the stack.
- The configuration has one static `my-ai-assistant` target at `host.docker.internal:8001` and inherits the default `/metrics` path.
- The README states that `/metrics` is unauthenticated and local-only, and documents starting the stack plus checking the Prometheus Targets page.

## Verification

```powershell
docker compose -f compose.observability.yaml config
docker compose -f compose.observability.yaml up -d
docker compose -f compose.observability.yaml ps
Start-Process http://127.0.0.1:9090/targets
```

With FastAPI running at `127.0.0.1:8001`, the `my-ai-assistant` target must become `UP` and `http_requests_total` must be queryable in the UI.

## References

- Prometheus Docker installation: https://prometheus.io/docs/prometheus/latest/installation/
- Prometheus configuration: https://prometheus.io/docs/prometheus/latest/configuration/configuration/#scrape_config
- Prometheus multi-target Docker example: https://prometheus.io/docs/guides/multi-target-exporter/
