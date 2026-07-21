# Backend README 실행 Runbook 설계

## 목적

`backend/README.md`를 사람이 로컬 백엔드 서비스를 실행하고, 상태를 확인하고,
문제가 생겼을 때 원인을 좁히는 데 사용하는 PowerShell 기반 runbook으로 다시 쓴다.

## 범위

- FastAPI, PostgreSQL, Prometheus, Grafana, `llama-server`의 로컬 실행 절차
- 최초 설정과 일상적인 빠른 실행의 분리
- 서비스별 정상 상태 확인 주소와 기대 결과
- 최소한의 상태 확인 및 증상별 진단 명령

## 범위 밖

- 테스트, 린트, 타입 검사 명령과 테스트 작성 규칙
- 인증 API, SSE 대화 API, PromQL의 상세 사용법
- 프로덕션 배포 또는 모니터링 보안 설계
- 프런트엔드 실행 안내

이 내용은 README의 실행 목적을 흐리고, 필요해지면 별도 문서에서 다루기로 한다.

## 문서 구조

### Quick start

초기 설정이 끝난 개발자가 서비스를 다시 띄우는 절차를 제공한다.

1. `docker compose up -d`로 PostgreSQL과 관측 스택을 시작한다.
2. 새 PowerShell 세션에서 `.env` 값을 로드하고 `llama-server`를 실행한다.
3. 별도 PowerShell 세션에서 `.env` 값을 로드하고 FastAPI를 실행한다.
4. FastAPI OpenAPI, Prometheus targets, Prometheus UI, Grafana URL을 열어 상태를 확인한다.

FastAPI와 `llama-server`는 호스트 프로세스이고, PostgreSQL·Prometheus·Grafana는
Compose 서비스라는 경계를 명시한다. 실행 순서는 FastAPI가 의존하는 데이터베이스와
LLM 서버가 먼저 준비되도록 한다.

### Setup

처음 한 번만 필요한 준비를 안내한다.

- Python 3.14, `uv`, Docker Desktop with Compose, `llama-server`, GGUF 모델이라는
  선행 조건
- `.env.example`을 `.env`로 복사한 뒤 `LLAMA_MODEL_PATH`와
  `POSTGRES_EXPORTER_PASSWORD`를 설정하는 단계
- `uv sync`로 의존성을 동기화하는 단계
- Compose 시작 후 `uv run alembic upgrade head`로 개발 데이터베이스 스키마를
  현재 리비전으로 올리는 단계

`.env`는 자동으로 Python 프로세스에 로드되지 않으므로, README는 현재 PowerShell
세션에 안전하게 환경 변수를 넣는 공통 코드 블록을 제공한다. Compose는 같은
디렉터리의 `.env`를 자체적으로 읽는다는 점도 구분해서 설명한다.

### Status and diagnostics

일상적인 확인과 대표 증상 진단만 다룬다.

- `docker compose ps`와 `docker compose logs <service>`
- `uv run alembic current`
- API에 접속할 수 없음: FastAPI 프로세스와 OpenAPI URL 확인
- Prometheus target이 `DOWN`: FastAPI 실행 여부 및 Prometheus 로그 확인
- Grafana에 데이터가 없음: Prometheus target과 수집 대기 시간 확인
- LLM 연결 실패: `llama-server` 실행, `LLM_BASE_URL`, `LLM_MODEL_NAME` 확인

각 항목은 증상, 확인 명령 또는 URL, 다음 조치 순서로 짧게 쓴다. 데이터 삭제,
볼륨 제거, 프로덕션 설정 변경처럼 되돌리기 어려운 명령은 포함하지 않는다.

### Reference

각 서비스의 역할과 로컬 주소를 한 표에 정리한다.

| 서비스 | 역할 | 주소 |
| --- | --- | --- |
| FastAPI | 애플리케이션 API | `http://127.0.0.1:8001` |
| Prometheus | 메트릭 수집·조회 | `http://127.0.0.1:9090` |
| Grafana | 대시보드 | `http://127.0.0.1:3000` |

## 명령 및 검증 기준

- 모든 명령은 PowerShell 문법으로 쓴다.
- 빠른 실행 단계에서는 FastAPI, Prometheus, Grafana를 모두 확인한다.
- FastAPI 검증은 `http://127.0.0.1:8001/openapi.json` 응답으로 한다.
- Prometheus 검증은 `http://127.0.0.1:9090/targets`에서 대상이 `UP`인지
  확인하는 것으로 한다.
- Grafana 검증은 `http://127.0.0.1:3000`에 접속해 대시보드를 열 수 있는지로 한다.
- README의 실제 명령을 보호하는 기존 문서 테스트는 새 runbook 구조에 맞춰 갱신한다.

## 성공 기준

- 처음 온 개발자가 `Setup`만 따라 `.env`, 의존성, 데이터베이스 스키마를 준비할 수 있다.
- 설정을 마친 개발자가 `Quick start`만 따라 다섯 서비스를 실행하고 세 관측 화면을
  확인할 수 있다.
- 대표적인 네 가지 장애 증상에서 다음 확인 명령 또는 URL을 바로 찾을 수 있다.
- README에 Bash 전용 문법, 테스트·품질 규칙, 오래된 별도 Compose 실행 절차가 없다.
