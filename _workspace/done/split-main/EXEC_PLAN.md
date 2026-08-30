# EXEC_PLAN: split-main

- **타입**: refactor
- **프로젝트**: project/dev-news
- **상태**: COMPLETED

## 목표

`main()` 하나가 114줄이었다. 수집·선별·요약·출력이 한 함수에 이어져 있어
어디까지가 한 단계인지 읽어야만 알 수 있고, 단계별로 시험할 수도 없다.

## 접근법

깔때기 단계 그대로 네 함수로 나눈다.

  collect_candidates(cfg)                수집 → 필터 → 중복 제거
  select_articles(articles, cfg, now, today)  점수 → 미소개 → 예약석·상한
  prepare_published(picked, cfg, no_ai)  본문 → 요약 → 분류 → 태깅
  write_outputs(published, cfg, now, out) 아카이브 → 인덱스 → 페이지 → 카탈로그

설정에서 파생되는 값(`top_n` · `gate_on` · `overpick` · `per_feed_page`)은
여러 단계가 함께 봐야 해서 `_gate_settings(cfg)` 하나에 모은다. 인자로 계속
넘기는 것보다 각 단계가 cfg에서 다시 읽는 편이 시그니처가 짧다.

**순수 이동이다.** 동작을 바꾸지 않는다.

## 결과 (2026-08-31)

  main()      114 → 33줄
  build.py    295 → 322줄 (단계 함수의 docstring이 늘어난 만큼)

로컬 전체 실행이 직전 회차와 완전히 같다 — 후보 240 → 142 → 미소개 95 →
선별 19, 본문 18/19, 출처 분포 동일. `--demo` 경로도 정상(기사 6건).
334개 테스트 통과.

**부수 정리.** `--demo`가 `load_config()`를 두 번 부르던 것을 한 번으로 합쳤다.

## 완료 기준

- main()이 40줄 아래로 내려간다 ✔
- 로컬 전체 실행 결과가 직전 회차와 같다 ✔
- --demo 경로가 동작한다 ✔
- verify-task 통과 ✔
- **완료일**: 2026-08-30T19:07:37.453Z
