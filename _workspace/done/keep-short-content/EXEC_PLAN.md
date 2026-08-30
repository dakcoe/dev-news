# EXEC_PLAN: keep-short-content

- **타입**: fix
- **프로젝트**: project/dev-news
- **상태**: COMPLETED

## 목표

본문을 멀쩡히 뽑아 놓고 버려서 요약이 통째로 비는 기사가 있다.

  mastodon 툿 2건    추출 136자  → 버려짐
  data4sci.com       추출 119자  → 버려짐
  phrack.org         추출  75자  → 버려짐 (프래그먼트 앵커)

`news/core/enrich.py`의 `MIN_CONTENT_CHARS = 200` 하드 컷 때문이다. 짧은 글은
원래 짧은 것이지 추출 실패가 아니다.

## 접근법

**바닥값을 200 → 80으로 낮춘다.** 실측 실패 4건 중 3건이 살아난다(136·136·119).
75자짜리 phrack 건은 프래그먼트 앵커라 실제로 본문을 못 읽은 경우이므로 계속
버리는 것이 맞다.

바닥값 자체를 없애지는 않는다 — 쿠키 배너·내비게이션 텍스트 같은 껍데기를
막는 역할이 남아 있다.

**추출본이 description보다 짧으면 쓰지 않는다.** 바닥값만 낮추면 85자 본문이
400자짜리 description을 밀어내는 역전이 생긴다. summarizer가
`content or description` 순으로 고르기 때문이다. 더 긴 쪽을 남긴다.

`_github_readme`도 같은 상수를 쓴다 — README가 짧다고 버릴 이유가 없으므로
같이 낮아지는 것이 맞다.

## 단계별 계획

1. (RED) `tests/test_short_content.py` — 실측 길이 4건 · 바닥값 미만 폐기 ·
   description보다 짧으면 폐기 · description이 없으면 짧아도 채택
2. `news/core/enrich.py` — 상수 조정, `enrich()`에서 길이 역전 방지
3. `node scripts/verify-task.js project/dev-news`
4. 커밋 → `complete-task.js`

## 완료 기준

- 119자 이상 본문이 살아남는다
- 80자 미만은 계속 버린다
- description보다 짧은 추출본이 description을 밀어내지 않는다
- verify-task 통과

## 결과 (2026-08-31)

`MIN_CONTENT_CHARS` 200 → 80, 채택 판단을 `usable_content()`로 일원화했다.
실제 URL로 확인: mastodon 툿 136자 · data4sci 119자 모두 살아남았다.

**길이 역전 방지가 함께 필요했다.** 바닥값만 낮추면 85자 본문이 400자짜리
description을 밀어낸다 — summarizer가 `content or description` 순으로 고르기
때문이다. 추출본이 description보다 짧으면 쓰지 않는다.

부수로 `[enrich]` 로그의 본문 집계를 채택 기준 통과분으로 바꿨다. 전에는
원시 추출본 수를 세어 실제 쓰인 수와 달랐다.
- **완료일**: 2026-08-30T18:16:27.087Z
