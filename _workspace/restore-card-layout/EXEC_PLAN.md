# EXEC_PLAN: restore-card-layout

- **타입**: fix
- **프로젝트**: project/dev-news
- **상태**: IN_PROGRESS
- **생성일**: 2026-08-06T10:41:53.278Z

## 목표

사용자 피드백: 고밀도 리스트보다 기존 카드형(오른쪽 썸네일) 레이아웃이 낫다.
Phase 3의 시각 변경만 되돌리고, spec-revamp의 기능(아카이브 검색·보관함 스냅샷·
Δ 표시·빈 요약 처리)과 백엔드 전체(샤딩·서킷 브레이커·candidates)는 유지한다.

## 접근법

template.html을 개편 전 카드 레이아웃(썸네일·2줄 스니펫·NEW/HOT 뱃지·상시 체크박스·
상태 카드·점수순 정렬) 기반으로 재작성하되 다음을 이식:
- savedMap 스냅샷(마이그레이션 포함) + 보관함의 아카이브 행
- 검색 시 아카이브 섹션 (search-index.json → 월 샤드 온디맨드)
- showDetail 공용화, GitHub 행은 점수 대신 +Δ 표시
- 유지되는 기존 개선: 레일 74/50px, 오버레이 없음, ckm 안읽음 체크박스, scrollbar-gutter

## 단계별 계획

1. template.html 재작성 (카드 복원 + 기능 이식)
2. tests/test_template.py의 Phase 3 어서션을 카드 복원 기준으로 교체
3. 실데이터 재렌더 + verify → 커밋 → push → complete

## 완료 기준

- 행에 썸네일·2줄 스니펫·뱃지·상태 카드가 복원됨
- 아카이브 검색·보관함 스냅샷·Δ 표시 정상 동작 유지
- pytest·린트 통과
