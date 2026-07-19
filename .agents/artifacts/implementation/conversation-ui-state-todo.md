# 대화 UI 상태 모델 작업 목록

- [x] `ConversationStatus`와 `ConversationView` 추가
- [x] App에서 `ConversationView[]`를 단일 상태 소스로 전환
- [x] 새 대화 생성 → `created` 등록·표시 전이
- [x] 사이드바 선택 → `displayed`/`hidden` 전이
- [x] 대화별 `isStreaming` 갱신 연결
- [x] `created`의 자동 히스토리 조회 생략
- [x] 첫 메시지 델타·SSE error 즉시 표시
- [x] 백그라운드 스트림 델타·오류 격리와 언마운트 취소 유지
- [x] 상태 모델과 수동 검증 절차 문서화
- [x] `npm run build`, `npm run lint`
- [ ] 브라우저 수동 시나리오 검증
