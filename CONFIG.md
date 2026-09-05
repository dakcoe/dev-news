# 설정 가이드

설정은 전부 `config.yaml`에 있다. 키는 `.env`(로컬) 또는 Actions 시크릿에 둔다.

## 수집 소스

| 소스 | 방식 |
|---|---|
| Hacker News | Firebase API `topstories` 상위 `hn_limit`개 |
| GitHub Trending | `github.com/trending` 일간. 지표는 스타 총수가 아니라 전일 대비 증가량 |
| Trendshift | `trendshift.io` 홈페이지의 일간 순위 25건. GitHub 트렌딩과 같은 저장소는 중복 제거에서 한 건으로 합쳐지고 교차 출처 가산을 받는다. 화면 라벨은 Trendshift |
| Lobste.rs | `hottest.json` |
| dev.to | `devto_tags`별 rising 글 |
| 긱뉴스 | `news.hada.io` RSS |
| RSS 피드 | `feeds`에 적은 주소 전부 |
| Anthropic | `anthropic.com/news` · `/engineering` HTML 직접 파싱 (RSS 미제공) |
| Reddit | 서브레딧 API (기본 꺼짐 — 아래 참고) |

`sources`에서 개별로 끄고 켠다.

### RSS 피드 추가

주소만 적으면 소스가 늘어난다.

```yaml
feeds:
  - name: 카카오 기술블로그
    url: https://tech.kakao.com/feed/
  - name: arXiv cs.AI
    url: https://rss.arxiv.org/rss/cs.AI
    page: false          # 후보 로그에만 쌓고 페이지에는 싣지 않는다
  - name: r/LocalLLaMA
    url: https://www.reddit.com/r/LocalLLaMA/.rss
    page: false
    user_agent: "dev-news/1.0 (personal feed aggregator)"   # 피드별 UA 덮어쓰기
```

- `name`을 생략하면 도메인이 출처 이름이 된다.
- 피드 하나가 죽어도 나머지는 계속 수집한다.
- `page: false`는 태그 어휘 도출용 코퍼스만 모을 때 쓴다. 후보 로그에는 남고 페이지에는 안 실린다.
- 글이 드문 공식 블로그는 `long_window`로 수집 창을 따로 늘린다 (기본 48시간, anthropic은 240시간).

### Reddit이 기본으로 꺼져 있는 이유

비인증 `hot.json` 요청이 집 IP에서도 403으로 막힌다. OAuth 앱을 만들면 되는데,
2026-08 기준 Reddit이 신규 앱 생성을 Responsible Builder Policy 승인 뒤로 막아 두었다.
승인을 받으면 `.env`에 `REDDIT_CLIENT_ID` · `REDDIT_CLIENT_SECRET`을 넣고 `reddit: true`로 켜면 된다. 코드는 준비돼 있다.

인증 없이 받는 공개 RSS(`r/LocalLLaMA/.rss`)는 별개 경로라 `feeds`에서 쓸 수 있다. 다만 Reddit은 낯선 User-Agent에 즉시 429를 주므로 위 예시의 UA 문자열을 유지한다.

## 필터

```yaml
keywords: [...]          # 제목·설명에 하나도 없으면 버린다 (단어 경계 매칭)
block_keywords:
  ko: [선거, 대선, ...]   # 부분 문자열 매칭
  en: [...]              # 단어 경계 매칭
```

- `github` / `devto` / `geeknews` / `rss` / `anthropic`은 개발 전용 소스라 `keywords` 화이트리스트는 건너뛴다. `block_keywords`는 이들에게도 적용된다.
- 차단어가 있어도 `keywords`가 하나라도 같이 걸리면 남긴다.
- 짧고 흔한 영어 단어(rest, data, set)는 `keywords`에 넣지 않는다. 단어 경계로도 못 막는다.
- 한국어 차단어는 다른 말에 파묻히는 모호어를 피한다. `배우`는 `배우다`에 걸린다.

## 선별과 점수

```yaml
scraper:
  top_n: 20          # 한 회차에 새로 추가할 기사 수
  per_source: 5      # 한 출처가 차지할 최대 개수 (rss 전체가 하나)
  per_feed_page: 2   # RSS 피드 하나가 차지할 최대 개수
  window_hours: 48   # 최근 몇 시간 내 발행분만
  keep_days: 30      # index.html에 굽는 기간. 저장은 무제한
```

점수는 화면에 표시하지 않고 `top_n` 선별의 정렬 기준으로만 쓴다.

```
기본점수 = 업보트 × 1.0 + 댓글 × 1.5 + 교차출처수 × 300
시간감쇠 = 8시간 이내 ×2.0 / 24시간 ×1.0 / 7일 ×0.5 / 그 이상 ×0.05
최종점수 = (기본점수 × 시간감쇠 + source_base) × source_weight
```

출처마다 숫자 단위가 다르다. GitHub는 수천, HN은 수백, 블로그는 0이다. 그대로 두면 GitHub가 상위를 독식하고 블로그 글은 바닥에 깔린다.

```yaml
source_base:       # 점수 개념이 없는 출처의 바닥값
  anthropic: 900
  rss: 420
source_weight:     # 과대·과소평가 보정 배수
  github: 0.35
```

앤트로픽 글이 자꾸 밀리면 `source_base.anthropic`을 올리고, GitHub가 너무 많으면 `source_weight.github`을 낮춘다.

**예약석**

```yaml
source_quota:
  github: 5
```

점수와 무관하게 자리를 보장하되 그 수를 넘지도 않는다.
`top_n: 20`에 `github: 5`면 일반 15건 + 트렌딩 5건이고, 트렌딩 후보가 4건뿐이면 19건으로 끝난다. 일반 기사가 빈자리를 메우지 않는다.

**LLM 분류 게이트** (`relevance_gate`, 기본 꺼짐)

요약 호출에 게재/제외 판정을 하나 더 받아 기술 밖 사건을 뺀다. 추가 호출은 없다.
무료 모델의 판정이 아직 흔들려 꺼 두었다. 켜면 `overpick`만큼 후보를 더 뽑아 둔다.

## 요약 모델

환경변수 하나로 공급자를 바꾼다. 로컬은 `.env`, Actions는 Variables의 `LLM_PROVIDER`.

| `LLM_PROVIDER` | 필요한 키 | 무료 한도 | 기본 모델 |
|---|---|---|---|
| `groq` (기본) | `GROQ_API_KEY` | 하루 1,000회 / 분당 30회 | `openai/gpt-oss-120b` |
| `openrouter` | `OPENROUTER_API_KEY` | 하루 50회 (크레딧 $10 넣으면 1,000회) | `meta-llama/llama-3.3-70b-instruct:free` |
| `gemini` | `GEMINI_API_KEY` | AI Studio 대시보드에서 확인 | `requirements.txt`의 `google-genai` 주석 해제 필요 |

모델만 바꾸려면 `LLM_MODEL`을 지정한다. 우선순위는 환경변수 `LLM_MODEL` → `config.yaml`의 `llm.model` → 공급자 기본값이다. 폴백 체인은 없다. 정해진 모델 하나만 끝까지 쓴다.

```yaml
llm:
  max_calls_per_run: 50   # 실행당 호출 상한. 하루 3회 × 50 = 150회로 무료 한도 안
  model:                  # 비우면 공급자 기본 모델
  pause_seconds: 6.0      # 호출 간격. gpt-oss는 2초면 절반이 429였다
```

- 429는 Retry-After만큼 기다려 최대 2회 재시도하고, 그래도 실패하면 그 회차의 요약을 통째로 멈춘다(서킷 브레이커). 남은 기사는 다음 회차로 넘어간다.
- 요약에 실패한 기사는 `seen.json`에 안 들어가므로 다음 회차에 자동으로 다시 시도된다. 단 `window_hours`를 넘기거나 출처 피드에서 내려가면 조용히 탈락한다.
- 모델이나 프롬프트를 바꿀 때는 `python scripts/eval_summary.py`로 요약 품질 회귀를 본다.

## 태그

기사마다 닫힌 어휘 20개에서 규칙 매칭으로 태그를 붙인다. LLM이 자유롭게 태그를 만들지 않는다.

| 그룹 | 태그 |
|---|---|
| AI | AI · LLM · 모델 · 에이전트 · AI 코딩 · 생성 미디어 · AI 안전 · 정책 |
| 개발 | 보안 · 개발 도구 · 웹 · 프론트엔드 · 백엔드 · 데이터 · 인프라 · 클라우드 · 언어 · 런타임 |
| 그 외 | 연구 · 벤치마크 · 하드웨어 · 칩 · 오픈소스 · 릴리스 · 출시 · 업계 · 비즈니스 · 커리어 · 문화 · 과학 · 우주 · 쇼케이스 |

- 매칭된 태그는 개수 제한 없이 전부 붙는다.
- 하위 태그(LLM, 에이전트 등)가 붙으면 상위 태그 AI가 자동으로 따라온다.
- GitHub 트렌딩은 출처 자체로 오픈소스 태그가 붙는다.
- `공개` · `도구` · `서버`처럼 요약문에 스치듯 등장하는 범용 명사는 원제목에 있을 때만 인정한다. LLM이 쓴 요약과 번역 제목은 오역으로 엉뚱한 태그를 만든 이력이 있다.

어휘와 패턴은 `news/core/tags.py`에 있다. 태거가 결정적이라 어휘를 고친 뒤 아래를 돌리면 지금까지 쌓인 기사 전부가 다시 태깅되고 검색 색인과 페이지도 재생성된다.

```bash
python scripts/retag.py
```

## 저장 구조

저장과 표시를 분리한다. 저장은 월별 샤드에 무제한 누적, 표시는 최근 `keep_days`.

```
data/articles/2026-09.json    # 이번 달 — 매 회차 새 기사가 맨 앞에 붙는다
data/articles/2026-08.json    # 지난 달 — 이후 수정하지 않는다 (retag만 예외)
data/candidates/2026-09.json  # 후보 전체와 판정 로그 (실리지 못한 기사 포함)
data/search-index.json        # 아카이브 검색용 경량 색인 — 제목·태그·월·출처만
data/seen.json                # 한 번 실린 URL — 영구 유지
data/fetch_health.json        # 본문 추출 실패 기록 (원인 분류용)
data/api_health.json          # 무료 API 링크 생존 확인 누적
docs/data/                    # 위 파일들의 Pages 서빙 사본 + apis.json
```

- 지난 달 샤드는 불변이라 git이 한 번만 저장하고 브라우저 캐시도 항상 적중한다. 단일 파일로 무한 성장시키면 GitHub의 100MB 제한에 걸린다.
- 검색 색인에는 페이지에 실린 기사만 들어간다. 후보 전체를 넣으면 연 15MB를 넘어 즉시 검색이 무거워진다.
- Actions가 매 회차 커밋하므로 실행 환경이 초기화돼도 누적이 유지된다.
- `data/`는 덮어쓰지 않는다. 누적 기록이 거기 있다.

## 알림

```yaml
alert:
  min_published: 10   # 이보다 적게 게시되면 Actions가 🟡 이슈를 연다
  silent_streak: 3    # 켜진 출처가 이 회차 수만큼 연속 0건이면 🟡 출처 침묵 이슈를 연다
```

출처별 수집 건수는 회차마다 `data/source_health.json`에 남는다(최근 30회차). 한 회차 0건은 타임아웃일 수 있어 기본 3회차(하루)를 본다.
GitHub 트렌딩·Trendshift·Anthropic은 HTML을 파싱하므로 상대 사이트가 화면을 바꾸면 에러 없이 0건이 된다. 그럴 때 이 알림이 잡는다.

## 광고

```yaml
ads:
  enabled: false
  provider: placeholder   # placeholder = 자리만 표시, adsense = 실제 광고
  client: ""              # ca-pub-숫자
  slot: ""                # 광고 단위 ID
  count: 1                # 오른쪽 레일에 쌓을 개수 (최대 3)
```

광고는 기사 사이가 아니라 오른쪽 레일에 붙고, 1200px 미만 화면에서는 그리지 않는다.

## 무료 API 목록

```yaml
apis:
  health:
    enabled: true
    per_run: 600          # 한 회차에 확인할 URL 수
    threshold: 2          # 연속 이 횟수만큼 죽어야 목록에서 뺀다
    max_drop_ratio: 0.3   # 한 소스에서 이 비율을 넘게 빠지면 필터를 건너뛴다
```

public-apis · public-apis-4Kr · awesome-free-llm-apis를 매 회차 파싱해 `docs/data/apis.json`으로 통째로 교체한다. 기사 파이프라인과 분리돼 있어 LLM 예산을 쓰지 않는다.
2,000여 건을 매번 다 두드리지 않고 `per_run`만큼 회전 확인한다. 하루 3회면 한 바퀴가 대략 하루다.

## 페이지 사용법

좌측 레일: **오늘의 뉴스 · 보관함 · 무료 API 목록 · 수집 소스 · GitHub 저장소**

- 정렬은 수집순 · 최신순 · 출처별. 수집순에서는 회차 구분선이 보인다.
- 기간(오늘 · 3일 · 7일 · 전체) · 안 읽음 · 태그 · 출처로 좁힌다. 태그는 여러 개 고르면 OR다.
- 검색창은 화면 밖 기사까지 찾는다. 색인을 한 번 받아 두고, 결과를 열 때 해당 월 샤드를 가져온다.
- 제목을 누르면 번역 요약이 오른쪽 패널에 열린다. 26시간 내 발행분은 제목 앞에 색점이 붙는다.
- **보관함** — 체크박스로 담고, 마크다운으로 복사할 수 있다.
- **읽음** — 상세나 원문을 열면 자동으로 읽음 처리되어 제목이 흐려진다. 눈 아이콘으로 직접 켜고 끈다.

보관함·읽음·태그 선택은 브라우저 로컬 저장소에 남는다. 페이지가 매 회차 새로 생성돼도 유지되지만, 기기·브라우저마다 따로 관리된다.
`file://`로 열면 아카이브 검색과 무료 API 목록은 동작하지 않는다. `data/`를 fetch하기 때문이다.
