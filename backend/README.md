# Backend

FastAPI, PostgreSQL, a local LLM, Prometheus, and Grafana를 로컬에서 실행하기 위한 runbook입니다.

## Quick start

[Setup](#setup)를 마친 뒤에는 아래 순서로 서비스를 실행합니다.

### 1. PostgreSQL과 관측 서비스를 시작합니다

```powershell
docker compose up -d
```

### 2. llama-server를 시작합니다

새 PowerShell 창에서 다음을 실행합니다.

```powershell
$envLines = Get-Content .env | Where-Object { $_ -match '^[A-Za-z_][A-Za-z0-9_]*=' }
foreach ($envLine in $envLines) {
  $parts = $envLine -split '=', 2
  Set-Item -Path ("Env:" + $parts[0]) -Value $parts[1]
}
llama-server -m $env:LLAMA_MODEL_PATH --alias $env:LLM_MODEL_NAME --port 8080
```

### 3. FastAPI를 시작합니다

별도 PowerShell 창에서 다음을 실행합니다.

```powershell
$envLines = Get-Content .env | Where-Object { $_ -match '^[A-Za-z_][A-Za-z0-9_]*=' }
foreach ($envLine in $envLines) {
  $parts = $envLine -split '=', 2
  Set-Item -Path ("Env:" + $parts[0]) -Value $parts[1]
}
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
uv run uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload --no-access-log
```

### 4. 전체 스택을 확인합니다

- `http://127.0.0.1:8001/openapi.json`이 JSON 문서를 반환합니다.
- `http://127.0.0.1:9090/targets`에서 `my-ai-assistant`와 `postgres` 대상이 `UP`입니다.
- `http://127.0.0.1:9090`에서 Prometheus 화면이 열립니다.
- `http://127.0.0.1:3000`에서 Grafana 대시보드가 열립니다.

## Setup

### Prerequisites

- Python 3.14
- `uv`
- Docker Desktop with Docker Compose
- `llama-server`와 호환되는 GGUF 모델

### 1. 로컬 설정을 만듭니다

`.env`가 아직 없다면 다음을 실행합니다.

```powershell
Copy-Item .env.example .env
```

`.env`에서 `LLAMA_MODEL_PATH`에 로컬 GGUF 파일의 절대 경로를 설정하고,
`POSTGRES_EXPORTER_PASSWORD`에 로컬 PostgreSQL exporter용 비밀번호를 설정합니다.
실제 비밀번호는 커밋하지 않습니다.

### 2. Python 의존성을 설치합니다

```powershell
uv sync
```

### 3. 데이터베이스 스키마를 적용합니다

```powershell
docker compose up -d
$envLines = Get-Content .env | Where-Object { $_ -match '^[A-Za-z_][A-Za-z0-9_]*=' }
foreach ($envLine in $envLines) {
  $parts = $envLine -split '=', 2
  Set-Item -Path ("Env:" + $parts[0]) -Value $parts[1]
}
uv run alembic upgrade head
```

Docker Compose는 현재 디렉터리의 `.env`를 자동으로 읽습니다. 반면 호스트에서 실행하는
`llama-server`와 FastAPI는 각 PowerShell 세션에서 위 환경 변수 로드 절차를 실행해야 합니다.
