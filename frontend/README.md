# Frontend

React와 Vite 기반의 최소 어시스턴트 UI입니다. 회원가입·로그인, 대화 목록,
메시지 히스토리, 새 대화, SSE 스트리밍 응답을 제공합니다.

메시지 입력창에서는 Enter로 전송하고 Shift + Enter로 줄바꿈합니다. 한글 등
IME 조합 중인 Enter는 메시지를 전송하지 않습니다.

## 실행

백엔드를 `vite.config.ts`의 `/api` 프록시 대상 포트에서 실행한 뒤 이
디렉터리에서 다음을 실행합니다.

```powershell
npm install
npm run dev
```

브라우저에서 `http://127.0.0.1:5173`을 엽니다. Vite 개발 서버는 `/api` 요청을
백엔드로 프록시합니다. 세션 인증은 서버가 설정한 httpOnly 쿠키를 사용하며,
비밀번호와 세션 토큰은 localStorage·sessionStorage에 저장하지 않습니다.
`http://localhost:5173`은 백엔드 Origin 허용 목록에 없으므로 사용하지 않습니다.

프로덕션 번들과 타입 검사는 다음 명령으로 수행합니다.

```powershell
npm run build
npm run lint
```
