# Backend Agents.md

## Environment

### Prerequisites

- Python 3.14
- `uv`
- `dotenvx`
- Docker Desktop with Docker Compose
- `llama-server` with a compatible GGUF model

### Setup

- `uv sync` - Sync dependencies.
- `docker compose up -d` - Start local services.
- `dotenvx run -- uv run alembic upgrade head` - Apply database migrations.

## Commands

- `dotenvx run -- uv run uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload --no-access-log` - Start the FastAPI development server.
- `dotenvx run -- powershell -NoProfile -Command 'llama-server -m $env:LLAMA_MODEL_PATH --alias $env:LLM_MODEL_NAME --port 8080'` - Start the local LLM server.
- `docker compose ps` - Show local service status.
- `docker compose logs <service>` - Show service logs.
- `dotenvx run -- uv run alembic current` - Show the current database revision.
- `dotenvx run -- uv run alembic revision --autogenerate -m "<description>"` - Generate a database migration.
- `dotenvx run -- uv run ruff format --check app tests` - Check formatting.
- `dotenvx run -- uv run ruff check app tests` - Run lint checks.
- `dotenvx run -- uv run pyright` - Run type checks.

## Testing

### Commands

- `dotenvx run -- uv run pytest` - Run all tests.
- `dotenvx run -- uv run pytest -m unit` - Run unit tests.
- `dotenvx run -- uv run pytest -m integration` - Run integration tests.
- `dotenvx run -- uv run pytest -m contract` - Run contract tests.

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
