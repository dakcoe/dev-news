# EXEC_PLAN: per-feed-user-agent

- **타입**: fix
- **프로젝트**: project/dev-news
- **상태**: COMPLETED

## 목표

consolidate-http에서 UA를 하나로 통일하면서 `r/LocalLLaMA` RSS 수집이 깨졌다.
오늘 아침 회차까지 8건씩 정상 수집되던 피드다.

## 원인 (실측)

  옛 rss UA   dev-news/1.0 (personal feed aggregator)           → 200  108,577B
  새 공용 UA  dev-news/1.0 (+https://github.com/dakcoe/dev-news) → 429  0B
  무작위 UA   some-random-client/9.9                             → 429  0B

무작위 UA도 429이므로 "로컬에서 여러 번 돌려 레이트리밋에 걸렸다"는 처음 추정은
틀렸다. 레딧이 처음 보는 UA에 즉시 429를 주고, 오래 써 온 문자열만 통과시킨다.

**`sources.reddit`(OAuth 스크래퍼)과는 다른 경로다.** 그쪽은 API 승인이 필요해
`false`로 꺼져 있고 이번 건과 무관하다. 이건 인증 없이 받던 공개 RSS다.

## 접근법

`config.yaml`의 피드 항목에 `user_agent`를 둘 수 있게 한다. 값이 있으면
그 피드에만 적용하고, 없으면 공용 UA를 쓴다.

  - name: r/LocalLLaMA
    url: https://www.reddit.com/r/LocalLLaMA/.rss
    page: false
    user_agent: "dev-news/1.0 (personal feed aggregator)"

**공용 UA를 되돌리지는 않는다.** 한 피드의 사정 때문에 전체를 바꾸면
consolidate-http가 얻은 것(정직한 UA + Accept 헤더로 hada.io 복구)을 잃는다.
예외는 예외로 둔다.

`http.get`이 이미 호출부 헤더를 우선하므로 래퍼는 고칠 필요가 없다.

## 단계별 계획

1. (RED) `tests/test_feed_user_agent.py` — 피드 UA가 전달될 것 ·
   없으면 공용 UA · 다른 피드에 새지 않을 것
2. `news/scrapers/rss.py` — `_one()`에서 `feed.get("user_agent")` 전달
3. `config.yaml` — r/LocalLLaMA에 UA 지정 + 이유 주석
4. 실제 수집으로 복구 확인
5. `node scripts/verify-task.js` → 커밋 → `complete-task.js`

## 완료 기준

- r/LocalLLaMA가 다시 수집된다
- UA를 지정하지 않은 피드는 공용 UA를 그대로 쓴다
- verify-task 통과


## 결과 (2026-08-31)

피드 항목의 `user_agent`를 `http.get`에 넘기도록 했다. 지정하지 않은 피드는
공용 UA를 그대로 쓴다. 테스트 3건으로 고정.

**복구는 확인하지 못했다.** 구현 직후 재시도했더니 옛 UA에도 403 Blocked가
났다. 몇 분 전에는 같은 UA로 200이었으므로, 원인이 UA만이 아니라 **IP 평판**
이라는 뜻이다. 진단하겠다고 반복 요청한 것이 스스로 차단을 불렀다.

  옛 UA   200 → (수 분 뒤) 403 Blocked
  새 UA   429
  무작위  429

**로컬에서는 더 판단할 수 없다.** Actions 러너는 IP가 다르므로 다음 정기 회차
로그(`[rss] r/LocalLLaMA …`)를 봐야 한다. 더 두드리면 악화되므로 테스트를
중단했다.

기능 자체는 남길 값어치가 있다 — 특정 피드만 UA를 달리해야 하는 상황은
레딧 말고도 생긴다. 다만 이번 건이 이걸로 해결된다는 보장은 없다.

**영향 범위는 작다.** r/LocalLLaMA는 `page: false` 코퍼스 전용이고, 1,292건 중
페이지에 실린 것은 2건뿐이다(교차 출처로 올라온 경우). 목적은 SPEC 1.2의
태그 어휘 도출용 코퍼스 축적이라 급하지 않다.
- **완료일**: 2026-08-30T19:39:00.489Z
