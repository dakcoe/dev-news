# EXEC_PLAN: remove-card-tag-filter-click

- **타입**: fix
- **프로젝트**: project/dev-news
- **상태**: IN_PROGRESS

## 목표

기사 카드 행의 태그 클릭 시 해당 태그 필터가 토글되는 동작을 제거한다 (사용자 요청).
사이드바 태그 패널의 필터링은 그대로 유지 — 카드의 태그는 표시 전용이 된다.

## 접근법

template.html 최소 수정: (1) `.tg[data-tg]` 클릭 핸들러 제거, (2) `.tg`를 표시 전용
스타일로 (cursor:pointer·hover 제거, 클릭이 행으로 통과하도록 pointer-events:none).
선택된 태그 강조(.hit)는 유지 — 사이드바에서 고른 태그가 카드에서 보이는 건 유용.

## 단계별 계획

1. RED: 템플릿에 카드 태그 클릭 핸들러가 없어야 한다는 테스트 작성
2. GREEN: 핸들러 제거 + 표시 전용 스타일
3. retag로 docs/index.html 재생성
4. verify → 커밋 → complete → push

## 완료 기준

- 카드 태그 클릭 시 필터 변화 없음 (핸들러 부재를 테스트로 고정)
- 사이드바 태그 필터·초기화 동작 기존 테스트 통과
