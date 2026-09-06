# EXEC_PLAN: quota-backfill-max

- **타입**: feat
- **프로젝트**: project/dev-news
- **상태**: COMPLETED

## 목표

예약석을 후순위 피드(Trendshift)로 메우는 개수에 상한을 둔다. 기본 2.
GitHub 트렌딩은 며칠씩 같은 목록이라 전부 seen에 있는 날이 흔하고, 그러면 5칸이 통째로 Trendshift가 된다 (2026-09-06 09:34 회차 실측).

## 접근법

- `pick`에 `quota_backfill_max: dict[str, int]` 추가. 예약석 1단계에서 후순위 항목이 이 수를 넘으면 더 뽑지 않는다.
  본진(트렌딩) 개수와 무관한 후순위 항목 개수 상한이다 — 트렌딩 4 + Trendshift 1 = 5, 트렌딩 0 + Trendshift 2 = 2.
- config `quota_backfill_max: {github: 2}`. 없으면 상한 없음(이전 동작).

## 단계별 계획

1. tests/test_pick_quota.py — 트렌딩 0이면 Trendshift 2건만, 트렌딩 4면 Trendshift 1, 설정 없으면 5 (RED)
2. select.pick 구현, build.py 두 호출부, config.yaml, CONFIG.md
3. verify-task → 커밋
4. 데이터: 09:34 회차의 Trendshift 5건 제거 후 로컬 회차 재생성 → push

## 완료 기준

- pytest 통과. 로컬 재수집 회차에서 github 항목이 Trendshift 최대 2건.
- **완료일**: 2026-09-06T06:58:10.540Z
