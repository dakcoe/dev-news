# EXEC_PLAN: fix-search-partial-render

- **타입**: fix
- **프로젝트**: project/dev-news
- **상태**: COMPLETED

## 목표

직전 IME 수정(조합 끝날 때만 렌더)의 부작용 해결: 맥 IME는 스페이스 등으로
커밋할 때까지 단어 전체 조합을 유지해서 검색이 계속 지연됨(스페이스-백스페이스
해야 적용). 조합 중에도 실시간 검색되면서 조합도 안 끊겨야 한다.

## 접근법

근본 원인(입력창까지 통째로 innerHTML 재생성)을 제거하는 부분 갱신으로 전환:
- 레이아웃(패싯+피드+아카이브) 생성을 layoutHTML()로 분리
- renderList() = .layout만 outerHTML 교체 + bind — 바(입력창)는 그대로
- 검색 oninput은 renderList()만 호출 → input이 교체되지 않으니 조합 가드
  (isComposing/compositionend) 자체가 불필요, 조합 중에도 즉시 필터링
- ensureIndex 콜백도 renderList()로 (인덱스 로드가 조합을 끊지 않도록)

## 단계별 계획

1. RED: layoutHTML/renderList 존재 + oninput 부분 갱신 테스트로 교체
2. GREEN: 분리·핸들러 교체 → retag → verify → 커밋 → complete → push

## 완료 기준

- 조합 중 실시간 검색 + 조합 유지 (구조적으로 input 미교체 보장)
- 전체 테스트 통과
- **완료일**: 2026-08-10T19:40:04.796Z
