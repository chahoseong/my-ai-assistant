# Dotenvx 로컬 환경 변수 실행 설계

## 목적

PowerShell 코드로 `.env`를 반복 로드하는 방식을 제거하고, `dotenvx` CLI가
FastAPI·Alembic·pytest·`llama-server` 프로세스에 `.env` 값을 주입하도록 한다.

## 결정

- `dotenvx`는 Python 의존성이 아닌 로컬 개발 CLI로 둔다.
- Windows 설치 명령은 `winget install dotenvx`로 문서화한다.
- 별도 실행 스크립트, Node 프로젝트 의존성, `.env` 암호화 기능은 추가하지 않는다.
- Docker Compose는 기존처럼 현재 디렉터리의 `.env`를 자동으로 읽으므로 바꾸지 않는다.
- `backend/README.md`와 `backend/AGENTS.md`의 호스트 프로세스 명령은
  `dotenvx run --`으로 시작한다.

## 명령 계약

```powershell
dotenvx run -- uv run uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload --no-access-log
dotenvx run -- uv run alembic upgrade head
dotenvx run -- uv run pytest
```

`llama-server`는 모델 경로와 별칭을 PowerShell 환경 변수에서 읽어 CLI 인수로
전달한다. 바깥 PowerShell이 값을 주입 전에 확장하지 않도록, dotenvx가 시작한
내부 PowerShell에서 그 식을 해석한다.

```powershell
dotenvx run -- powershell -NoProfile -Command 'llama-server -m $env:LLAMA_MODEL_PATH --alias $env:LLM_MODEL_NAME --port 8080'
```

작은따옴표는 바깥 PowerShell의 `$env:` 확장을 막는다. dotenvx가 `.env`를 주입한
뒤에만 내부 PowerShell이 해당 값을 확장한다.

## 문서 변경

- README `Setup`의 선행 조건과 설치 단계에 `dotenvx`를 추가한다.
- README의 FastAPI·`llama-server`·Alembic 명령에서 수동 환경 변수 로더를 제거한다.
- README에 Compose와 dotenvx의 책임 경계를 한 문단으로 설명한다.
- AGENTS.md에서 수동 로더를 제거하고, Alembic·서버·테스트·품질 명령을 dotenvx
  실행 방식으로 변경한다.

## 검증

- README 계약 테스트는 `dotenvx run --`으로 시작하는 FastAPI·llama-server 명령과
  하나의 Uvicorn 명령, 하나의 `--no-access-log`를 확인한다.
- `dotenvx` 설치 후 `dotenvx --version`을 실행한다.
- 실제 `.env`를 출력하지 않고 `dotenvx run -- uv run alembic current`와
  `dotenvx run -- uv run pytest`를 실행한다.
- Ruff와 Pyright도 dotenvx 환경에서 실행한다.

## 범위 밖

- `.env` 파일 값 또는 `.env.example` 변수 구조 변경
- CI/CD와 프로덕션 secret 관리 변경
- dotenvx의 암호화·키 파일 기능
- Docker Compose와 데이터베이스 설정 변경

## 성공 기준

- 문서에 PowerShell 환경 변수 파싱 반복 코드가 없다.
- 모든 호스트 기반 백엔드 명령이 dotenvx를 통해 `.env`를 받는다.
- `llama-server` 명령이 dotenvx 주입 뒤에 모델 경로와 모델 별칭을 확장한다.
- Python 패키지 메타데이터와 잠금 파일은 변경하지 않는다.
