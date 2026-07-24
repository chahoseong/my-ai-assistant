# my-ai-assistant

멀티턴 대화와 SSE 스트리밍을 제공하는 로컬 AI 어시스턴트입니다.

모델이 날씨처럼 외부 도구를 선택하면, 내부 도구 이름이나 입력값을 노출하지 않고
사용자용 진행 문구를 스트리밍합니다. 도구 호출이 끝난 뒤에는 최종 답변으로 상태를 대신합니다.

- `backend/`: FastAPI와 PostgreSQL 기반 API
- `frontend/`: React·Vite 기반 브라우저 UI

각 서비스의 설치와 실행 방법은 [백엔드 안내](backend/README.md)와
[프런트엔드 안내](frontend/README.md)를 참고하세요.
