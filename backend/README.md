# Backend

## Prerequisites

- Python 3.14 (uv가 `.python-version`에 맞는 인터프리터를 관리한다.)
- llama.cpp의 `llama-server`
- `gemma-4-E4B-it-qat-q4_0.gguf` 모델 파일

## Run

Install the project dependencies:

```powershell
uv sync
```

In a separate terminal, start the OpenAI-compatible local model server:

```powershell
llama-server -m gemma-4-E4B-it-qat-q4_0.gguf --port 8080
```

Then start FastAPI:

```powershell
uv run fastapi dev app/main.py
```

## Verify streaming

Send a request with buffering disabled:

```powershell
curl.exe -N -X POST http://127.0.0.1:8000/api/chat -H "Content-Type: application/json" -d "{\"message\":\"한국의 수도는 어디야?\"}"
```

The response is an SSE stream containing `data:` events as text is generated.

## Quality checks

```powershell
uv run pytest
uv run ruff format --check app tests
uv run ruff check app tests
uv run pyright app tests
```
