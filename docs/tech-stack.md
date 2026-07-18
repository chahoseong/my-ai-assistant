# tech-stack.md

프로젝트를 진행하며 적용하고 배울 원칙은 [software-development-principles.md](software-development-principles.md)를 참고한다.

## Frontend

백엔드 기능을 경험하기 위한 지원 도구다 (학습 대상 아님, 빠르고 실용적으로 구현).

- **언어**: TypeScript 6.x
- **런타임**: Node.js 24 LTS
- **프레임워크**: React 19.2
- **빌드 도구**: Vite 8.1

## Backend

- **언어**: Python 3.14.x
- **패키지 매니저**: uv 0.11.x
- **웹 프레임워크**: FastAPI 0.13x
- **동시성**: asyncio, threading (Python 표준 라이브러리)
- **데이터 검증/직렬화**: Pydantic 2.13.x
- **실시간 통신**: SSE(`sse-starlette`), WebSocket(FastAPI 내장)
- **데이터베이스**: PostgreSQL 18.4 (Docker Compose로 실행, `postgres:18.4` 이미지)
- **ORM/드라이버**: SQLAlchemy 2.0.51 (async) + asyncpg 0.31.0
- **DB 마이그레이션**: Alembic 1.18.x
- **린트/포맷**: Ruff 0.15.x
- **타입 체크**: Pyright 1.1.x
- **테스트**: pytest 9.1.x + httpx 0.28.x + pytest-asyncio 1.4.x
- **인증/인가**: 세션 쿠키 (`secrets` 표준 라이브러리) + Argon2id 비밀번호 해싱 (argon2-cffi 25.1.x)

<!--
- **캐시**: 미정
-->

## Agent

- **Model**: `google/gemma-4-E4B-it-qat-q4_0-gguf`
- **Inference Engine**: llama.cpp + Vulkan 백엔드
- **Orchestration**: Pydantic AI 2.9.1
