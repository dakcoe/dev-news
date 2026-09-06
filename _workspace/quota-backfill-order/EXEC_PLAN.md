# EXEC_PLAN: quota-backfill-order

- **타입**: feat
- **프로젝트**: project/dev-news
- **상태**: IN_PROGRESS

## 목표

github 예약석 5칸을 GitHub 트렌딩 항목으로 먼저 채우고, 남는 자리만 Trendshift 전용 항목으로 메운다.
Trendshift는 유용성이 낮은 저장소도 섞여 있어 트렌딩과 동등하게 스타 수로 경쟁시키면 안 된다.

## 접근법

- `select.pick`에 `quota_backfill: dict[str, list[str]]` 추가. 예약석 1단계에서 해당 출처 항목을
  두 무리로 나눈다: 본진(피드 없음, 또는 merged_sources에 본 출처가 있음 = 트렌딩에도 오른 것)과
  후순위(feed가 backfill 목록에 있고 트렌딩과 안 겹침). 본진을 점수순으로 먼저, 남는 칸을 후순위로.
- 둘 다에 오른 저장소는 본진이다 — 교차 출처 가산과 결이 같다.
- config `quota_backfill: {github: [Trendshift]}`. 비우면 동작이 이전과 같다.

## 단계별 계획

1. tests/test_pick_quota.py — 트렌딩 우선, 부족분만 Trendshift, 양쪽에 오른 건은 본진, 상한 5 유지, 설정 없으면 기존 동작 (RED)
2. select.pick 구현, build.py 두 호출부에 전달, config.yaml
3. CONFIG.md 예약석 절
4. verify-task → 커밋 → push

## 완료 기준

- pytest 전체 통과. 트렌딩 후보 3건 + Trendshift 10건이면 트렌딩 3 + Trendshift 2.
