# 구현 계획: 대화 UI 상태 모델

## 목표

새 대화는 생성 응답을 받은 즉시 정식 대화로 목록에 등록하고 화면에 표시한다.
첫 메시지의 SSE 델타와 오류는 즉시 보이며, 이 초기 흐름에서는 선택 변경에
따른 자동 히스토리 조회가 낙관적 메시지를 덮어쓰지 못하게 한다. 다른 대화를
선택하면 기존 스트림은 백그라운드에서 계속되고, 로그아웃·언마운트 시에만
취소한다.

## 상태 모델

서버 응답 `Conversation`은 변경하지 않는다. App이 화면용 모델을 소유한다.

```ts
type ConversationStatus = 'created' | 'displayed' | 'hidden'

type ConversationView = Conversation & {
  status: ConversationStatus
  isStreaming: boolean
}
```

- `created`: 새 대화의 첫 메시지 흐름으로 현재 열려 있다. 스트림 완료 뒤에도
  유지하며, 선택 변경으로 인한 자동 히스토리 조회를 생략한다.
- `displayed`: 사이드바에서 선택해 보는 일반 대화다. 선택 시 히스토리를
  조회한다.
- `hidden`: 현재 화면에 보이지 않는 대화다. 백그라운드 스트림은 가능하지만
  화면 메시지·오류를 갱신하지 않는다.
- `isStreaming`: 해당 대화의 SSE 응답 생성이 진행 중인지 나타낸다.

`ConversationView[]`가 화면 대화 상태의 단일 진실 소스다. 현재 대화는
`status !== 'hidden'`인 항목으로 도출하며, 별도의 `selectedConversationId`와
중복 보관하지 않는다.

## 작업 순서

### 작업 1: App의 대화 전이 모델 정리

`frontend/src/lib/types.ts`와 `frontend/src/App.tsx`에 화면용 대화 타입과 상태
전이를 추가한다.

수용 기준:

- 목록 최초 로드 대화는 `hidden`으로 등록된다.
- 새 대화 생성 응답은 즉시 `created`, `isStreaming: false`로 등록·표시된다.
- 사이드바 선택은 이전 표시 대화를 `hidden`, 대상 대화를 `displayed`로 바꾼다.
- 스트림 시작·종료 콜백은 해당 대화의 `isStreaming`만 변경한다.

의존성: 없음. 예상 파일: `types.ts`, `App.tsx`.

### 작업 2: ChatView의 조회·스트림 규칙을 상태 모델에 연결

`frontend/src/components/ChatView.tsx`가 활성 `ConversationView`와 상태 변경
콜백을 받도록 바꾼다. `created` 대화의 선택 직후에는 자동 히스토리 GET을
생략하고, SSE `done` 또는 `error` 뒤에는 명시적으로 최종 히스토리를
동기화한다.

수용 기준:

- 새 대화 첫 메시지의 사용자 말풍선, 델타, SSE 오류가 즉시 표시된다.
- `displayed` 대화 선택 시에만 자동 히스토리 조회가 실행된다.
- A 스트리밍 중 B를 선택해도 A의 델타·오류는 B에 표시되지 않고, A는
  `hidden + isStreaming` 상태로 계속 실행된다.
- 409 같은 스트림 시작 전 HTTP 오류는 두 임시 말풍선을 제거하고 초안을
  보존한다.
- ChatView 언마운트 시 모든 스트림을 abort한다.

의존성: 작업 1. 예상 파일: `ChatView.tsx`, 필요 시 `sse.ts`.

### 작업 3: 문서와 수동 검증 갱신

설계 문서에 `created/displayed/hidden`과 `isStreaming`의 책임, 첫 메시지
히스토리 조회 생략 규칙을 기록한다.

수용 기준:

- 상태 전이와 백그라운드 스트림 정책이 문서에 명시된다.
- 기존 `127.0.0.1:5173` Origin 및 8001 프록시 안내는 유지된다.

의존성: 작업 1~2. 예상 파일: 설계 문서, 필요 시 프런트엔드 README.

## 검증 체크포인트

- `npm run build`
- `npm run lint`
- 새 대화: 생성 직후 목록·화면 표시, 첫 델타와 SSE 오류 표시
- A 생성 중 B 선택: B에서 입력 가능, A 완료 뒤 B 선택 유지, A 재선택 시
  저장된 최종 응답 표시
- 409: 임시 말풍선 제거와 초안 보존
- 로그아웃: 진행 중 모든 스트림 취소 및 보호 화면 접근 불가

프런트엔드 자동 테스트는 이번 스펙 범위에서 제외되어 있으므로, 위 항목은
브라우저 수동 검증과 빌드·린트로 확인한다.

## 위험과 대응

| 위험 | 대응 |
| --- | --- |
| 상태와 선택 ID를 따로 저장해 불일치 | `ConversationView[]`만 화면 상태의 진실 소스로 사용 |
| 첫 히스토리 GET이 낙관적 메시지를 덮음 | `created` 상태에서는 선택 효과의 자동 GET 생략 |
| 배경 A 이벤트가 B에 섞임 | 이벤트·오류·최종 동기화 전에 활성 대화 ID 확인 |
| 로그아웃 뒤 늦은 콜백 | 언마운트 cleanup에서 모든 AbortController 취소 |
