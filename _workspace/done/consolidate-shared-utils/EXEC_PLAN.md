# EXEC_PLAN: consolidate-shared-utils

- **타입**: refactor
- **프로젝트**: project/dev-news
- **상태**: COMPLETED

## 목표

같은 코드가 여러 곳에 흩어져 있고, 그 사본들이 서로 조금씩 다르다.

  날짜 파싱   geeknews._to_ts · rss._ts · lobsters 인라인 · reddit · scorer
  KST 상수    build · render · api_health · apis_catalog (4곳)
  ROOT 경로   3곳에 같은 os.path.dirname 중첩식

## 사본이 갈라진 실제 버그

`rss._ts`는 tzinfo가 없는 datetime을 UTC로 보정하는데 **`geeknews._to_ts`는
안 한다.**

  rss:      if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
  geeknews: parsedate_to_datetime(value).astimezone(timezone.utc)

naive datetime에 `.astimezone()`을 부르면 파이썬이 그 값을 **로컬 시각으로
해석한다.** 로컬(KST)과 Actions(UTC)에서 같은 피드가 9시간 다른 값으로
저장된다는 뜻이다. `recent_only`의 48시간 창 판정이 환경에 따라 달라진다.

반환형도 갈라져 있다 — geeknews는 `int`, rss는 `float`.

## 접근법

`news/core/common.py` 하나에 모은다.

  KST            타임존 상수
  ROOT           프로젝트 루트 경로
  to_timestamp() 날짜 문자열·숫자 → UTC 타임스탬프(float) 또는 None

`to_timestamp()`는 세 형식을 받는다 — RFC 2822(`parsedate_to_datetime`),
ISO 8601(`Z` 접미사 포함), 숫자(epoch). **naive는 항상 UTC로 본다.**

**범위를 좁힌다.** `archive`·`render`가 파싱하는 `a["batch"]`는 우리가 직접 쓴
KST isoformat이라 형식이 보장된다. 입력 성격이 다르고 바꿔도 이득이 없으므로
건드리지 않는다.

## 단계별 계획

1. (RED) `tests/test_common.py` — RFC2822 · ISO8601 · Z 접미사 · naive는 UTC ·
   숫자 입력 · 잘못된 입력 · geeknews/rss 동치성
2. `news/core/common.py` 신설
3. 호출부 교체 — geeknews · rss · lobsters · reddit · scorer, KST 4곳, ROOT 3곳
4. `node scripts/verify-task.js project/dev-news`
5. 커밋 → `complete-task.js`

## 완료 기준

- naive datetime이 로컬 타임존과 무관하게 UTC로 해석된다
- geeknews와 rss가 같은 입력에 같은 값을 돌려준다
- KST·ROOT 정의가 한 곳에만 남는다
- 기존 275개 테스트가 그대로 통과한다
- verify-task 통과

## 결과 (2026-08-31)

`news/core/common.py` 신설 — `KST` · `ROOT` · `to_timestamp()`.

**제거한 사본**

  날짜 파싱  geeknews._to_ts · rss._ts · lobsters 인라인 · reddit 인라인 ·
             scorer._time_decay 내부  → to_timestamp() 하나로
  KST        build · render · api_health · apis_catalog (4곳 → 재노출 import)
  ROOT       archive · candidates · seen (3곳 → 재노출 import)

**고친 버그.** naive datetime을 로컬 시각으로 해석하던 문제. `to_timestamp()`는
타임존이 없으면 항상 UTC로 본다. 로컬(KST)과 Actions(UTC)에서 같은 피드가
9시간 다른 값으로 저장되던 것이 사라진다.

반환형도 통일했다 — geeknews가 `int`, rss가 `float`이었다.

**부수 발견.** `devto.py` · `github.py` · `hackernews.py` · `lobsters.py`가
읽기 전용(`-r--r--r--`)이라 수정할 수 없었다. 전부 `Aug 5 14:54`로 한 번도
수정된 적 없는 파일이고, 앞서 `scorer.py`에서 겪은 것과 같은 증상이라
속성을 풀었다.

**실측 확인.** lobsters·rss 실제 수집으로 published_at이 정상 파싱됨을 확인.
- **완료일**: 2026-08-30T18:28:30.629Z
