# EXEC_PLAN: fix-mobile-layout

- **타입**: fix
- **프로젝트**: project/dev-news
- **상태**: COMPLETED
- **생성일**: 2026-08-19T16:46:53.079Z

## 목표

모바일(≤820px)에서 뉴스 카드 본문 칸이 98px까지 쪼그라들어 제목이 한 단어씩 세로로
줄바꿈되는 레이아웃 붕괴를 고친다. 390px 뷰포트에서 카드 제목·요약이 정상 폭으로 읽혀야 한다.

## 접근법

Chrome DevTools 모바일 에뮬레이션(390×844)으로 실측한 원인:

1. `.row` 그리드가 모바일에서 `auto minmax(0,1fr) auto` — 액션 버튼(`.acts`)을
   가로로 눕혔지만 여전히 **옆 칸**이라 108px을 차지, 본문(`.mid`)이 98px만 남는다.
2. 좌측 레일(`.rail`)이 모바일에서도 세로 74px 고정 — 390px 화면의 19%를 소모.

수정은 전부 `news/template.html`의 `@media (max-width:820px)` 블록:

- `.acts`를 `grid-column`으로 카드 하단 전체 폭 행으로 내린다 (본문이 1fr 전부 회수).
- `.rail`을 하단 고정 내비게이션 바로 전환하고 `.scroll`에 하단 여백을 준다.
- 라이브 CSS 주입으로 에뮬레이터에서 먼저 검증한 뒤 템플릿에 반영한다.

docs/index.html은 생성물이므로 직접 수정하지 않는다 — 다음 Actions 실행 때 반영된다.

## 단계별 계획

1. 에뮬레이터에서 수정 CSS를 라이브 주입해 390px 화면 스크린샷으로 검증
2. `news/template.html` 미디어쿼리 블록 수정
3. 재현 테스트 추가 (tests/ — 템플릿 모바일 규칙 존재 검증)
4. `node scripts/verify-task.js project/dev-news` 통과 확인
5. 커밋 + complete-task

## 완료 기준

- 390px 에뮬레이션에서 카드 제목이 정상 가로 폭으로 표시 (`.mid` ≥ 250px)
- 가로 스크롤 없음
- 데스크톱(≥821px) 레이아웃은 변화 없음
- verify-task.js (pytest + ruff) 통과
- **완료일**: 2026-08-19T16:53:06.296Z
