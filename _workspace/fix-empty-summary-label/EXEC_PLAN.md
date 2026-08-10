# EXEC_PLAN: fix-empty-summary-label

- **타입**: fix
- **프로젝트**: project/dev-news
- **상태**: IN_PROGRESS

## 목표

요약이 빈 기사에 표시되는 "(요약 생성 실패 — 원문을 확인하세요)" 문구를 정확한 안내로 교체한다.
실제 원인은 생성 실패가 아니라 본문 추출 불가(페이월·영상·JS 전용 페이지)에 대한 LLM의 정상적인
"덧붙일 것 없음" 응답이다 — 2026-08 실측 9건 전부 content 없음(HN발 페이월/유튜브/논문/마스토돈).

## 접근법

render.py의 폴백 문구만 교체 (최소 변경). summarizer의 "없음 → 빈 문자열" 설계와
render의 폴백 동작 자체는 유지 — 문구가 상황을 정확히 설명하도록만 수정.

## 단계별 계획

1. RED: 빈 summary+description 기사가 새 문구로 렌더되는 실패 테스트 작성
2. GREEN: render.py 문구 교체
3. retag 플로우로 docs/index.html 재생성 (기게시 9건에 즉시 반영)
4. verify-task.js 통과 확인
5. 커밋 → complete-task → push

## 완료 기준

- 빈 요약 기사 카드에 "(본문이 공개되지 않은 기사 — 원문을 확인하세요)" 표시
- 기존 테스트 전체 통과, docs 재생성 완료
