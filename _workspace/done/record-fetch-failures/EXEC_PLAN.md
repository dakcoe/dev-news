# EXEC_PLAN: record-fetch-failures

- **타입**: feat
- **프로젝트**: project/dev-news
- **상태**: COMPLETED

## 목표

본문 수집 실패가 `print`로만 나가고 사라진다. 왜 실패했는지 나중에 알 방법이
없다.

**이번 세션에서 실제로 겪은 비용이다.** 실패 원인을 분류하려고 최근 250건
URL에 요청을 다시 날리는 재현 스크립트를 따로 짜서 돌려야 했다. 그 결과가
403 봇 차단 4건 · 404 죽은 링크 3건 · SPA 4건 · 짧은 본문 4건이었고, 이후
작업 세 개(block-dead-links · keep-short-content · 링크 판정)의 근거가 됐다.

기록만 있었으면 조회 한 번으로 끝날 일이었다.

## 접근법

`data/fetch_health.json`에 회차별 결과를 누적한다. **추가 요청은 0회다** —
이미 enrich가 받아 온 응답에서 알 수 있는 것만 적는다.

사유는 `classify()`가 주는 판정보다 잘게 나눈다. 게재 판단에는 403과 200이
똑같이 `ok`지만, 진단할 때는 구분돼야 한다.

| reason | 뜻 |
|--------|-----|
| ok | 본문을 얻었다 |
| dead | 404·410·DNS 실패 (게재 제외 대상) |
| blocked | 401·403·429 — 살아 있지만 봇 차단 |
| unavailable | 5xx·타임아웃 |
| empty | 200인데 추출 실패 |
| short | 추출은 됐지만 채택 기준 미달 |
| github | raw README 경로 (판정 제외) |

회차 기록은 최근 30회만 남긴다. 무한 누적하면 커밋마다 파일이 커진다.

**실패해도 회차를 죽이지 않는다.** 기록은 부가 기능이므로 파일이 깨졌거나
쓰기에 실패해도 파이프라인은 그대로 진행한다 (api_health와 같은 원칙).

## 단계별 계획

1. (RED) `tests/test_fetch_health.py` — 사유 분류 · 회차 상한 30 ·
   깨진 파일 복구 · 쓰기 실패가 예외를 던지지 않을 것
2. `news/core/fetch_health.py` 신설 — `record()` · `load()`
3. `news/core/enrich.py` — `_fetch_one`이 사유를 함께 돌려주고 `enrich`가 기록
4. 로컬 전체 실행으로 파일 생성 확인
5. `node scripts/verify-task.js` → 커밋 → `complete-task.js`

## 완료 기준

- 회차마다 `data/fetch_health.json`에 사유별 집계와 실패 URL이 남는다
- 추가 HTTP 요청이 없다
- 기록이 실패해도 회차가 죽지 않는다
- 회차 기록이 30개를 넘지 않는다
- verify-task 통과

## 결과 (2026-08-31)

`news/core/fetch_health.py` 신설, `enrich`가 회차마다 `data/fetch_health.json`에
기록한다. `_fetch_one`이 응답 코드까지 돌려주도록 확장했다 — 추가 요청은 0회다.

**첫 실행에서 바로 값을 했다.**

  집계: ok 9 · github 5 · blocked 5
  실패 상세: blocked | geeknews | https://news.hada.io/topic?id=33042  (외 4건)

세션 초반에 추측만 하고 넘어갔던 "hada.io가 로컬 python-requests에는 403인데
Actions에서는 통과하는 것 같다"가 이제 데이터로 남는다. 다음 Actions 회차의
기록과 비교하면 확정할 수 있다.

`github`는 raw README 경로라 실패가 아니므로 상세 목록과 요약 줄 양쪽에서 뺐다.
- **완료일**: 2026-08-30T18:55:51.159Z
