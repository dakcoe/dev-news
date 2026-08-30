# EXEC_PLAN: consolidate-http

- **타입**: refactor
- **프로젝트**: project/dev-news
- **상태**: COMPLETED

## 목표

HTTP 요청이 12개 파일 17군데에서 제각각 나간다. User-Agent만 10종이다.

  hackernews.py   UA 없음               ← 봇 차단 위험
  devto.py        discord-news-bot/1.0  ← 옛 디스코드 봇 잔재
  lobsters.py     news-scraper/1.0
  github.py       Mozilla/5.0 … (문자열이 중간에 잘려 있다)
  rss/geeknews    dev-news/1.0
  anthropic       Chrome/124 (Windows)
  enrich          Chrome/124 (Mac)
  candidates      dev-news
  api_health      Mozilla/5.0 (compatible; …)

흩어진 것 자체보다 **함께 빠져 있는 것들**이 문제다.

| 빠진 것 | 결과 |
|---------|------|
| 재시도 | 피드 하나가 순간 502만 떠도 그 블로그는 그날 통째로 빠진다 |
| content-type 검사 | PDF·이미지가 그대로 trafilatura로 들어간다 |
| `resp.content` | charset 없는 응답을 ISO-8859-1로 추정 → 한국어 본문 깨짐 |

`requests`는 HTTP 헤더에 charset이 없으면 ISO-8859-1로 추정한다. HTML meta에만
UTF-8을 선언한 한국어 블로그가 여기 걸린다.

## 접근법

`news/core/http.py`에 얇은 래퍼 하나를 둔다. **requests를 감싸기만 하고
동작을 바꾸지 않는다** — 호출부가 17군데라 의미가 달라지면 회귀 범위가 넓다.

  get(url, **kw)   기본 UA·Accept 부착, 재시도, 응답 그대로 반환

**재시도는 보수적으로.** 2회, 지수 백오프(1s → 2s). 재시도 대상은 5xx와
연결 오류뿐이다 — 4xx는 다시 걸어도 같은 답이고, 429는 상대가 쉬라는 뜻이라
회차 안에서 조르지 않는다.

**UA는 정직하게 하나로.** `dev-news/1.0 (+https://github.com/dakcoe/dev-news)`.
브라우저 위장(Chrome/124)은 쓰지 않는다 — 상대가 막을 근거를 주는 편이 낫고,
차단당하면 fetch_health에 blocked로 남아 진단이 된다.

**예외 두 곳을 남긴다.**
- `api_health.py` — 링크 생존 확인은 재시도하면 판정이 흐려진다(1회 확인이
  전제). 자체 헤더·타임아웃을 유지한다.
- `github.py` — 트렌딩 페이지가 봇 UA에 다르게 응답할 수 있어 실측 전까지
  기존 UA를 유지한다.

## 단계별 계획

1. (RED) `tests/test_http.py` — 기본 헤더 · 5xx 재시도 · 4xx 즉시 포기 ·
   연결 오류 재시도 · 재시도 상한 · 백오프 호출 · params/timeout 전달
2. `news/core/http.py` 신설
3. 호출부 교체 — hackernews · devto · lobsters · rss · geeknews · anthropic ·
   reddit · candidates · enrich (github·api_health 제외)
4. `enrich`에 content-type 검사와 `resp.content` 적용
5. 로컬 전체 실행 — 수집 건수가 이전 회차와 비슷한지 확인
6. `node scripts/verify-task.js` → 커밋 → `complete-task.js`

## 완료 기준

- 모든 수집 요청이 같은 UA를 쓴다
- 5xx·연결 오류에 2회까지 재시도한다
- 4xx·429는 재시도하지 않는다
- HTML이 아닌 응답이 본문 추출로 들어가지 않는다
- 로컬 전체 실행 수집 건수가 직전 회차(247건)와 크게 다르지 않다
- verify-task 통과

## 결과 (2026-08-31)

`news/core/http.py` — 기본 헤더 + 5xx·연결오류 2회 재시도(1s→2s).
교체: hackernews · devto · lobsters · rss · geeknews · anthropic ·
candidates · enrich. 예외 3곳: `github.py`(트렌딩 UA 실측 전 유지) ·
`api_health.py`(1회 확인이 전제라 재시도 금지) · `reddit.py`(기본 비활성 +
자체 OAuth 흐름).

**본문 추출이 13/19 → 18/19로 올랐다.** 원인은 `Accept` 헤더다 —
`fetch_health` 기록이 직전 회차 `blocked 5`(전부 hada.io)에서 이번 회차
`ok 14 · github 5`로 바뀌었다. 세션 내내 "hada.io가 로컬에서 403"이라고
넘겼던 것이 UA가 아니라 Accept 부재 때문이었다는 뜻이다.

**인코딩 버그는 실재했다.** charset 없는 응답을 재현해 확인:

  resp.text    → 'íêµì´ ë³¸ë¬¸ì ëë¤...'
  resp.content → '한국어 본문입니다...'

`requests`는 charset이 없으면 ISO-8859-1로 추정한다. `resp.content`로 넘기면
trafilatura·BeautifulSoup이 자체 감지를 쓴다(둘 다 bytes 처리 확인).

**관찰 필요.** `r/LocalLLaMA` RSS가 새 UA에 429를 준다. 옛 UA는 200이라
UA 거부처럼 보이지만, 로컬에서 전체 실행을 여러 번 돌려 새 UA가 레이트리밋에
걸렸을 가능성이 높다(403이 아니라 429다). 코퍼스 전용 피드(`page: false`)라
페이지에는 영향이 없고, 실패는 `[rss] … 실패` 로그로 드러난다. Actions는 하루
3회라 조건이 다르므로 다음 회차를 보고 판단한다.
- **완료일**: 2026-08-30T19:01:56.032Z
