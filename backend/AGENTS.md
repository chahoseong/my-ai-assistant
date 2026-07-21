# Backend Agents.md

## Environment

### Prerequisites

- Python 3.14
- `uv`
- Docker Desktop with Docker Compose
- `llama-server` with a compatible GGUF model

### Setup

- `uv sync` - Sync dependencies.
- `docker compose up -d` - Start local services.
- `$envLines = Get-Content .env | Where-Object { $_ -match '^[A-Za-z_][A-Za-z0-9_]*=' }; foreach ($envLine in $envLines) { $parts = $envLine -split '=', 2; Set-Item -Path ("Env:" + $parts[0]) -Value $parts[1] }` - Load `.env` into the current PowerShell session.
- `uv run alembic upgrade head` - Apply database migrations.

## Commands

- `uv run uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload --no-access-log` - Start the FastAPI development server.
- `llama-server -m $env:LLAMA_MODEL_PATH --port 8080` - Start the local LLM server.
- `docker compose ps` - Show local service status.
- `docker compose logs <service>` - Show service logs.
- `uv run alembic current` - Show the current database revision.
- `uv run alembic revision --autogenerate -m "<description>"` - Generate a database migration.
- `uv run ruff format --check app tests` - Check formatting.
- `uv run ruff check app tests` - Run lint checks.
- `uv run pyright` - Run type checks.

## Testing

### Commands

- `uv run pytest` - Run all tests.
- `uv run pytest -m unit` - Run unit tests.
- `uv run pytest -m integration` - Run integration tests.
- `uv run pytest -m contract` - Run contract tests.

### Requirements

- Place tests in the matching `tests/<domain>/` directory.
- Mark tests as `unit`, `integration`, or `contract`.
- Cover normal, failure, and boundary scenarios for changed behavior.
- Cover each changed branch or document why it cannot be tested.
- Add regression tests for fixed bugs.
- Write unit tests for isolated behavior.
- Write integration tests when behavior depends on interactions between components or systems.
- Write both when isolated behavior and its integration can fail independently.
- Avoid duplicate tests that cover the same failure signal.
- Do not skip, weaken, or delete tests to make the suite pass.
