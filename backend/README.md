# Backend

## Prerequisites

- Python 3.14 (uv가 `.python-version`에 맞는 인터프리터를 관리한다.)
- llama.cpp의 `llama-server`
- `gemma-4-E4B_q4_0-it.gguf` 모델 파일 (Hugging Face 모델 이름: `google/gemma-4-E4B-it-qat-q4_0-gguf`)

## Configuration

The API sends the following model identifier to the OpenAI-compatible server by default:

```text
google/gemma-4-E4B-it-qat-q4_0-gguf
```

Override any connection value with environment variables before starting FastAPI:

| Variable | Default |
| --- | --- |
| `LLAMA_MODEL` | `google/gemma-4-E4B-it-qat-q4_0-gguf` |
| `LLAMA_BASE_URL` | `http://127.0.0.1:8080/v1` |
| `LLAMA_API_KEY` | `llama.cpp` |

For example:

```powershell
$env:LLAMA_BASE_URL = "http://127.0.0.1:8080/v1"
```

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

## Stream errors

If llama-server cannot be reached or fails while generating text, the HTTP response
has already started and cannot change to an HTTP 500 status. The API instead sends a
safe SSE error event:

```text
event: error
data: Unable to generate a response.
```

The server logs the detailed exception with the `chat_stream_failed` event name.
The SSE response deliberately does not expose the internal exception message.

## Quality checks

```powershell
uv run pytest
uv run ruff format --check app tests
uv run ruff check app tests
uv run pyright app tests
```
