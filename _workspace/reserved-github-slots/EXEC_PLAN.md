# EXEC_PLAN: reserved-github-slots

- **타입**: fix
- **프로젝트**: project/dev-news
- **상태**: COMPLETED

## 목표

GitHub 트렌딩 자리를 일반 기사와 분리해 고정한다.

  일반 15 + 트렌딩 5 = 20
  트렌딩이 중복 제외로 4건뿐이면 → 15 + 4 = 19 (일반으로 메우지 않는다)

## 현재 동작과의 차이

`config.yaml`에 이미 `source_quota: github: 5`가 있어 5칸을 먼저 확보하긴 한다.
그런데 `pick()`의 2단계가 `len(picked) >= top_n`까지 채우므로, github가 4건만
확보되면 **남은 1칸을 일반 기사가 가져가 20건이 된다.** 원하는 건 19건이다.

즉 지금은 "우선권"이고, 필요한 것은 "예약석"이다.

## 접근법

2단계의 목표를 `top_n`이 아니라 **`top_n - 예약분 합계`**로 바꾼다.

  일반 상한 = top_n - sum(quota.values())   # 20 - 5 = 15
  최종      = 확보한 예약분 + 일반 15건

예약 출처가 부족하면 그만큼 전체 건수가 준다. 반대로 예약 출처에 후보가 넘쳐도
`quota`를 넘지 않는다(기존 `per_source` 상한이 그대로 작동).

`quota`가 비면 일반 상한이 `top_n` 그대로라 기존 동작과 같다.

## 단계별 계획

1. (RED) `tests/test_pick_quota.py` — 15+5 분배 · 트렌딩 부족 시 19건 ·
   일반 부족 시 · quota 없을 때 기존 동작 · quota가 top_n보다 클 때
2. `build.py:pick()` 2단계 상한 변경
3. pytest 전체 → 커밋 → 아카이브

## 완료 기준

- github 후보가 충분하면 정확히 일반 15 + github 5 = 20건
- github 후보가 4건이면 19건 (일반이 메우지 않는다)
- `quota`가 비면 기존과 동일하게 top_n건
- pytest 전체 통과


## 결과 (2026-08-31)

`pick()`의 2단계 목표를 `top_n`에서 `top_n - 예약분 합계`로 바꾸고, 예약 출처는
2단계에서 아예 제외했다(quota가 상한 역할도 하게 된다). `config.yaml`은 이미
`source_quota: github: 5`였으므로 값 변경은 없다 — 의미만 바뀌었다.

**테스트 작성 중 발견:** 처음 쓴 축소 테스트가 `per_source=15` 덕분에 구현 전에도
통과했다. 예약석이 아니라 출처별 상한이 건수를 줄이고 있었던 것이라, 자리와
후보가 모두 남은 상황(`per_source=30`)을 쓰는 테스트를 따로 추가했다 —
`test_short_reserved_is_not_backfilled_even_with_room`.

**분류 게이트와의 상호작용.** 게이트가 켜지면 `overpick`만큼 더 뽑으므로 마지막에
`top_n`으로 줄여야 하는데, 앞에서 그냥 자르면 예약 비율이 깨진다. 그래서 같은
`pick()`을 한 번 더 태운다. 게이트가 꺼져 있으면 절단 자체가 없다.
