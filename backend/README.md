# Backend

## Prerequisites

- Python 3.14 (uv가 `.python-version`에 맞는 인터프리터를 관리한다.)
- llama.cpp의 `llama-server`
- `gemma-4-E4B_q4_0-it.gguf` 모델 파일

## Run

Install the project dependencies:

```powershell
uv sync
```

In a separate terminal, start the OpenAI-compatible local model server:

```powershell
llama-server -m "path\to\gemma-4-E4B_q4_0-it.gguf" --port 8080
```

Then start FastAPI:

```powershell
uv run fastapi dev app/main.py
```

## Verify streaming

In Windows PowerShell, set the pipeline output encoding to UTF-8 before sending Korean JSON to `curl.exe`. Otherwise, PowerShell can replace non-ASCII characters with `?` before the request reaches the server.

```powershell
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

'{"message":"한국의 수도는 어디야?"}' |
  curl.exe -N -X POST "http://127.0.0.1:8000/api/chat" `
    -H 'Content-Type: application/json' `
    --data-binary '@-'
```

The response is an SSE stream containing `data:` events as text is generated.

## Quality checks

```powershell
uv run pytest
uv run ruff format --check app tests
uv run ruff check app tests
uv run pyright app tests
```
