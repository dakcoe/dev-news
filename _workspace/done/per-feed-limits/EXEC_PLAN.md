# EXEC_PLAN: per-feed-limits

- **타입**: fix
- **프로젝트**: project/dev-news
- **상태**: COMPLETED

## 목표

한 매체가 RSS 자리를 독식한다. 최근 10배치 196건 중 rss 43건인데 그중
**The Decoder 한 곳이 30건(70%)**이다.

  The Decoder 30 · Simon Willison 5 · Hugging Face 4
  카카오 1 · OpenAI 1 · 토스 1 · Google AI Blog 1

## 원인

출처별 상한 `per_source: 5`는 **`source` 기준**이라 rss 전체를 5건으로 묶을 뿐,
그 5칸을 어느 피드가 가져가는지는 통제하지 않는다. 글을 많이 쓰는 매체일수록
후보가 많아 점수 경쟁에서 이긴다.

수집 단계의 `per_feed: 8`도 전역 단일값이라 매체별 차등이 없다.

## 접근법

**선별 단계에 피드별 상한을 더한다.** 수집을 줄이는 것이 아니라(후보는 많을수록
좋다) 한 배치에 실리는 수를 제한한다.

  per_source: 5      기존 — source(rss) 단위
  per_feed_page: 2   추가 — feed(The Decoder) 단위

`feed` 키가 있는 아이템에만 적용한다. rss와 anthropic 스크래퍼가 이 키를
채우고, hackernews·github 등은 채우지 않으므로 영향이 없다.

`source_quota`(예약석)에는 적용하지 않는다 — 예약은 출처 단위 보장이고,
github에는 feed 키가 없다.

## 단계별 계획

1. (RED) `tests/test_per_feed.py` — 피드별 상한 · feed 없는 아이템은 무제한 ·
   source 상한과 함께 작동 · 설정이 없으면 기존 동작
2. `build.py:pick()` — feed 단위 카운터 추가
3. `config.yaml` — `scraper.per_feed_page`
4. 최근 10배치 재현으로 분포 확인
5. `node scripts/verify-task.js` → 커밋 → `complete-task.js`

## 완료 기준

- 한 피드가 배치당 상한을 넘지 않는다
- feed 키가 없는 출처는 영향받지 않는다
- 설정이 없으면 기존과 동일하게 동작한다
- verify-task 통과

## 결과 (2026-08-31)

`pick()` 2단계에 피드 단위 카운터를 더하고 `scraper.per_feed_page: 2`를 뒀다.

**최근 10배치 재현 — 피드별 게재 수**

  The Decoder      27 → 15
  Simon Willison    5 →  5
  Anthropic         2 →  2
  Hugging Face      2 →  2
  OpenAI · Google AI Blog · 토스 · 카카오   각 1 → 1

**재현의 한계를 밝혀 둔다.** 합계가 40 → 28로 줄었는데, 이는 이미 게재된
기사만 후보로 넣어 재선별했기 때문이다. 대체할 다른 rss 후보가 표본에 없다.
실제 회차는 훨씬 큰 후보 풀에서 뽑으므로 빈 자리는 다른 매체·출처가 채운다.

수집 단계의 `per_feed: 8`은 건드리지 않았다 — 후보는 많을수록 좋고, 문제는
선별이었다.
- **완료일**: 2026-08-30T18:18:31.354Z
