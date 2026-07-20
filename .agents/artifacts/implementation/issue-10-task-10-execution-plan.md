# Issue #10 Task 10: Disable Duplicate Server Access Logs

**Goal:** Address PR #11 review feedback by ensuring the documented FastAPI server commands emit only the application's structlog JSON access log.

## Scope

- Replace both documented development restart commands that use `fastapi dev` with Uvicorn commands that include `--no-access-log`.
- Add a regression test for the documented server command contract.
- Manually verify a real HTTP request produces one JSON access log and no Uvicorn access log.

## Acceptance criteria

- [ ] README contains no `fastapi dev` server command.
- [ ] Each documented Uvicorn development command includes `--no-access-log`.
- [ ] A real request to the documented command produces one `http_request_complete` JSON log line and no Uvicorn access log line.

## Verification

```powershell
uv run pytest tests/test_runtime_logging.py -q
uv run ruff format --check app tests
uv run ruff check app tests
uv run pyright app tests
uv run pytest -q
```

## Files likely touched

- `backend/README.md`
- `backend/tests/test_runtime_logging.py`

## References

- PR #11 review: duplicate Uvicorn access logs
- Uvicorn settings: https://www.uvicorn.org/settings/
