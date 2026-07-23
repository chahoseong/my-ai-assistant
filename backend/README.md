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
dotenvx run -- powershell -NoProfile -Command 'llama-server -m $env:LLAMA_MODEL_PATH --alias $env:LLM_MODEL_NAME --port 8080 --jinja'
```

도구 호출에는 모델별 chat template를 적용하는 `--jinja`가 필요합니다. 이 프로젝트는
llama.cpp `9982 (99f3dc322)`와 Gemma 도구 호출을 함께 검증했습니다. 다른 버전이나
모델로 바꾸면 실제 도구 호출 smoke를 다시 실행하세요.

백엔드는 첫 응답 완료 시 llama-server의 `GET /props`에서 컨텍스트 한계
`default_generation_settings.n_ctx`를 lazy 조회하고 프로세스 수명 동안 캐시합니다.
llama-server를 다른 `-c` 값으로 재시작했다면 캐시를 갱신하기 위해 FastAPI도
함께 재시작합니다. `/props` 조회가 실패해도 채팅 응답은 계속 동작합니다.

### 3. FastAPI를 시작합니다

별도 PowerShell 창에서 다음을 실행합니다.

```powershell
dotenvx run -- uv run uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload --no-access-log
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
- `dotenvx`
- Docker Desktop with Docker Compose
- `llama-server`와 호환되는 GGUF 모델

### 1. 로컬 설정을 만듭니다

`.env`가 아직 없다면 다음을 실행합니다.

```powershell
Copy-Item .env.example .env
```

`.env`에서 `LLAMA_MODEL_PATH`에 로컬 GGUF 파일의 절대 경로를 설정하고,
`POSTGRES_EXPORTER_PASSWORD`에 로컬 PostgreSQL exporter용 비밀번호를 설정합니다.
날씨 도구를 사용하려면 Nominatim 정책에 맞는 식별 가능한
`NOMINATIM_USER_AGENT`도 설정합니다. 실제 비밀번호와 연락처 정보는 커밋하지 않습니다.

### 2. dotenvx를 설치합니다

```powershell
winget install dotenvx
```

### 3. Python 의존성을 설치합니다

```powershell
uv sync
```

### 4. 데이터베이스 스키마를 적용합니다

```powershell
docker compose up -d
dotenvx run -- uv run alembic upgrade head
```

Docker Compose는 현재 디렉터리의 `.env`를 자동으로 읽습니다. 호스트에서 실행하는
FastAPI와 `llama-server`는 `dotenvx run --`이 `.env`를 각 프로세스에 주입합니다.

## 도구와 운영 경계

- 날씨 도구는 도시명을 Nominatim으로 좌표화한 뒤 Open-Meteo를 호출합니다. Nominatim의
  public endpoint는 application-wide 1 rps, 좌표 cache, 식별 가능한 User-Agent를 전제로
  합니다. 위치 검색 데이터 출처는 채팅 UI에 항상 표시됩니다.
- 상세한 도구 단계, 입력값, 결과를 브라우저 SSE나 로그에 노출하지 않습니다. 외부 도구
  결과는 모델 지시문이 아니라 신뢰하지 않는 데이터로 취급합니다.

## 관측성

Grafana의 **Tool** row는 다음 운영 질문을 답합니다.

- 어떤 모델용 도구가 `success`, `failed`, `timeout`, `denied` 결과로 얼마나 호출되는가
- 어떤 도구의 p95 호출 시간이 느려졌는가
- agent가 `tool_calls_limit=5`를 자주 초과하는가

`agent_tool_calls_total`과 `agent_tool_duration_seconds`의 label은 도구 이름과 고정된
outcome만 사용합니다. 입력 인자와 반환 결과는 metric이나 구조화 로그에 기록하지 않습니다.
도구 호출의 상세 실시간 trace UI는 제공하지 않습니다.

## Migration과 rollback

`20260723_0004` migration은 모델이 다음 turn에 복원할 정본 이력을 `model_messages`에
저장합니다. 새 애플리케이션은 이 테이블을 사용하므로 먼저 migration을 적용한 뒤 새
애플리케이션을 배포해야 합니다.

이 migration의 downgrade는 `model_messages` 테이블과 정본 이력을 삭제합니다. 따라서
일상적인 application rollback 절차로 자동 실행하지 마세요. 이전 애플리케이션과의 호환성을
확인하고 백업을 확보한 뒤에만 downgrade를 검토합니다.
