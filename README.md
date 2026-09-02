[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/dakcoe/dev-news/pulls)

# dev-news

매일 00시·08시·16시(KST)에 개발·AI 뉴스를 수집해 정적 페이지 한 장으로 만들어 두는 도구.
GitHub Actions에서 돌면 서버가 필요 없고, `python build.py` 한 줄로 로컬에서도 똑같이 돌아간다.

**보기:** https://dakcoe.github.io/dev-news/

```
수집 → 필터 → 점수화 → 중복 제거 → 본문 추출 → LLM 요약 → 태그 → 월별 저장 → docs/index.html
```

## 수집 소스

| 소스 | 방식 |
|---|---|
| Hacker News | Firebase API `topstories` 상위 N개 |
| GitHub Trending | `github.com/trending` 일간 (지표는 스타 총수가 아니라 전일 대비 증가량) |
| Lobste.rs | `hottest.json` |
| dev.to | 태그별 rising 글 |
| 긱뉴스 | `news.hada.io` RSS |
| RSS 피드 | `config.yaml`의 `feeds`에 적은 주소 전부 |
| Anthropic | `anthropic.com/news` · `/engineering` HTML 직접 파싱 (RSS 미제공) |
| Reddit | 서브레딧 API (기본 꺼짐 — 아래 참고) |

`config.yaml`의 `sources`에서 개별로 끄고 켠다.

### RSS 피드 추가

주소만 적으면 소스가 늘어난다.

```yaml
feeds:
  - name: 카카오 기술블로그
    url: https://tech.kakao.com/feed/
  - name: arXiv cs.AI
    url: https://rss.arxiv.org/rss/cs.AI
    page: false          # 후보 로그에만 쌓고 페이지에는 싣지 않는다
```

`name`을 생략하면 도메인이 출처 이름이 된다. 피드 하나가 죽어도 나머지는 계속 수집한다.
`page: false`는 태그 어휘 도출용 코퍼스만 모으고 싶을 때 쓴다.

글이 드문 공식 블로그는 `long_window`로 수집 창을 따로 늘릴 수 있다 (기본 48시간, anthropic은 10일).

### Reddit이 기본으로 꺼져 있는 이유

비인증 `hot.json` 요청이 집 IP에서도 403으로 막힌다. OAuth 앱을 만들면 되는데,
2026-08 기준 Reddit이 신규 앱 생성을 Responsible Builder Policy 승인 뒤로 막아 두었다.
승인을 받으면 `.env`에 `REDDIT_CLIENT_ID` · `REDDIT_CLIENT_SECRET`을 넣고 `reddit: true`로 켜면 된다. 코드는 준비돼 있다.

인증 없이 받는 공개 RSS(`r/LocalLLaMA/.rss`)는 별개 경로라 `feeds`에서 쓸 수 있다.

## 빠른 시작 (로컬)

```bash
pip install -r requirements.txt

# 레이아웃만 확인 — 네트워크도 API 키도 필요 없음
python build.py --demo

# 실제 수집 (요약 없이, 키 불필요)
python build.py --no-ai
```

전체 실행에는 키가 필요하다. `.env.example`을 복사해 `.env`로 이름을 바꾸고 키를 채우면 끝이다.

```powershell
copy .env.example .env      # 윈도우 (맥/리눅스는 cp)
notepad .env                # GROQ_API_KEY=gsk_... 채우기
python build.py
```

`.env`는 `.gitignore`에 들어 있어 깃허브에 올라가지 않는다.
이미 셸에 환경변수가 설정돼 있으면 그쪽이 우선이고, GitHub Actions에서는 Secrets가 쓰인다.

결과는 `docs/index.html`. 브라우저로 그냥 열면 된다. 아카이브 검색과 무료 API 목록은 `data/`를 fetch하므로 `file://`로 열면 동작하지 않는다.

> 로컬에서 `python build.py`를 돌리면 `data/seen.json`에 기록이 남는다. 같은 날 Actions가 또 돌면 차순위 기사가 추가로 실린다.

## GitHub Pages에 올리기

1. 깃허브에서 빈 저장소 `dev-news`를 만든다 (public — Pages 무료 조건)

2. 이 폴더를 올린다

   ```bash
   git init
   git add .
   git commit -m "첫 커밋"
   git branch -M main
   git remote add origin https://github.com/<아이디>/dev-news.git
   git push -u origin main
   ```

3. **Settings → Secrets and variables → Actions → New repository secret**
   - 이름 `GROQ_API_KEY`, 값은 https://console.groq.com 에서 발급한 키

4. **Settings → Pages** — Source `Deploy from a branch`, Branch `main` / 폴더 `/docs`

5. **Settings → Actions → General → Workflow permissions** 를 `Read and write`로 (Actions가 결과를 커밋한다)

6. **Actions 탭 → 매일 뉴스 수집 → Run workflow** 로 한 번 수동 실행

   2~3분 뒤 `https://<아이디>.github.io/dev-news/` 로 접속된다.
   이후로는 07:00 · 15:00 · 23:00 UTC(= 16시 · 00시 · 08시 KST) 하루 세 번 자동 실행된다.

> 무료 계정의 스케줄 실행은 러너가 붐빌 때 수십 분 밀릴 수 있다.
> 지난 실행의 **Re-run jobs**는 그 시점 코드 스냅샷으로 돌아 push가 거부되므로, 수동 실행은 항상 Run workflow 버튼을 쓴다.

회차가 정상 종료됐는데 게시가 `alert.min_published`(기본 10건)보다 적으면 Actions가 이슈를 열어 알린다.
요약 한도 초과나 후보 고갈로 몇 건만 올라오는 조용한 열화를 잡기 위한 장치다.

## 요약 모델 바꾸기

환경변수 하나로 공급자를 바꾼다. Actions에서는 **Settings → Variables**에 `LLM_PROVIDER`를 넣으면 된다.

| `LLM_PROVIDER` | 필요한 키 | 무료 한도 | 기본 모델 |
|---|---|---|---|
| `groq` (기본) | `GROQ_API_KEY` | 하루 1,000회 / 분당 30회 | `openai/gpt-oss-120b` |
| `openrouter` | `OPENROUTER_API_KEY` | 하루 50회 (크레딧 $10 넣으면 1,000회) | `meta-llama/llama-3.3-70b-instruct:free` |
| `gemini` | `GEMINI_API_KEY` | AI Studio 대시보드에서 확인 | `requirements.txt`의 `google-genai` 주석 해제 필요 |

모델만 바꾸려면 `LLM_MODEL` 변수를 지정한다. Groq는 모델을 종종 정리하므로,
실패 로그에 `model_decommissioned`가 보이면 https://console.groq.com/docs/models 에서 현재 ID를 확인해 넣는다.

호출 예산은 `config.yaml`의 `llm.max_calls_per_run`(기본 50)으로 실행당 상한을 건다.
하루 3회 실행이 무료 일일 한도를 다 쓰지 않도록 한 것이다.
요약에 실패한 기사는 seen에 남지 않아 다음 회차에 자동으로 다시 시도된다.

## 선별과 점수

```yaml
scraper:
  top_n: 20          # 한 회차에 새로 추가할 기사 수
  per_source: 5      # 한 출처가 차지할 최대 개수
  per_feed_page: 2   # RSS 피드 하나가 차지할 최대 개수
  window_hours: 48   # 최근 몇 시간 내 발행분만
  keep_days: 30      # index.html에 굽는 기간 (저장은 무제한)
```

`keywords`는 제목·설명에 하나도 걸리지 않으면 버리는 화이트리스트, `block_keywords`는 정치·사건 등 비개발 주제를 거르는 차단어다.
`github` / `devto` / `geeknews` / `rss` / `anthropic`은 개발 전용 소스라 화이트리스트는 건너뛰고 차단어만 적용한다.

점수는 화면에 표시하지 않고 `top_n` 선별의 정렬 기준으로만 쓴다.

```
기본점수 = 업보트 × 1.0 + 댓글 × 1.5 + 교차출처수 × 300
시간감쇠 = 8시간 이내 ×2.0 / 24시간 ×1.0 / 7일 ×0.5 / 그 이상 ×0.05
최종점수 = (기본점수 × 시간감쇠 + source_base) × source_weight
```

출처마다 숫자 단위가 달라 (GitHub는 수천, HN은 수백, 블로그는 0) `source_base`로 바닥값을, `source_weight`로 배수를 준다.
앤트로픽 글이 자꾸 밀리면 `source_base.anthropic`을 올리고, GitHub가 너무 많으면 `source_weight.github`을 낮춘다.

**예약석(`source_quota`)** — 점수와 무관하게 자리를 보장하되 그 수를 넘지도 않는다.
`github: 5`면 일반 15건 + 트렌딩 5건이고, 트렌딩 후보가 4건뿐이면 19건으로 끝난다 (일반이 메우지 않는다).

## 태그

기사마다 닫힌 어휘 20개(AI · LLM · 에이전트 · AI 코딩 · 보안 · 웹 · 인프라 …)에서 규칙 매칭으로 태그를 붙인다.
LLM이 자유롭게 태그를 만들지 않으므로 결과가 결정적이고, 매칭된 태그는 개수 제한 없이 전부 붙는다.

어휘와 패턴은 `news/core/tags.py`에 있다. 고친 뒤 아래를 돌리면 지금까지 쌓인 기사 전부가 새 어휘로 다시 태깅된다.

```bash
python scripts/retag.py
```

페이지에서 태그 칩을 여러 개 고르면 OR로 필터되고, 선택은 브라우저에 저장돼 다음 방문 때 기본 뷰가 된다.

## 저장 구조

저장과 표시를 분리한다. 저장은 월별 샤드에 무제한 누적, 표시는 최근 `keep_days`.

```
data/articles/2026-09.json    # 이번 달 — 매 회차 새 기사가 맨 앞에 붙는다
data/articles/2026-08.json    # 지난 달 — 이후 수정하지 않는다 (retag만 예외)
data/candidates/2026-09.json  # 후보 전체와 판정 로그
data/search-index.json        # 아카이브 검색용 경량 색인 (제목·태그·월·출처)
data/seen.json                # 한 번 실린 URL — 영구 유지
docs/data/                    # 위 파일들의 Pages 서빙 사본 + apis.json
```

Actions가 매 회차 커밋하므로 실행 환경이 초기화돼도 누적이 유지된다.

> `data/`는 덮어쓰지 말 것. 누적 기록이 거기 있다.

## 페이지 사용법

좌측 레일: **오늘의 뉴스 · 보관함 · 무료 API 목록 · 수집 소스 · GitHub 저장소**

- 정렬은 수집순 · 최신순 · 출처별. 수집순에서는 회차 구분선이 보인다
- 기간(오늘 · 3일 · 7일 · 전체) · 안 읽음 · 태그 · 출처로 좁힌다
- 검색창은 화면 밖 기사까지 찾는다. 색인을 한 번 받아 두고, 결과를 열 때 해당 월 샤드를 가져온다
- 제목을 누르면 번역 요약이 오른쪽 패널에 열린다. 26시간 내 발행분은 제목 앞에 색점이 붙는다
- **보관함** — 체크박스로 담고, 마크다운으로 복사할 수 있다
- **읽음** — 상세나 원문을 열면 자동으로 읽음 처리되어 제목이 흐려진다. 눈 아이콘으로 직접 켜고 끈다
- **무료 API 목록** — public-apis · public-apis-4Kr · awesome-free-llm-apis를 매 회차 파싱한 카탈로그. 죽은 링크는 회차마다 일부씩 확인해 뺀다

보관함·읽음·태그 선택은 브라우저 로컬 저장소에 남는다. 페이지가 매 회차 새로 생성돼도 유지되지만, 기기·브라우저마다 따로 관리된다.

## 문제가 생기면

**긱뉴스가 0건** — RSS 주소가 바뀐 것이다. `news/scrapers/geeknews.py`의 `FEED_CANDIDATES`에 새 주소를 추가한다.

**요약이 전부 실패** — 로그의 `[summarizer]` 줄과 첫 `오류` 줄을 본다. 401이면 키, `model_decommissioned`면 모델 ID 문제다. `--no-ai`로 돌리면 요약 없이도 페이지는 나온다.

**push가 GH013으로 거부됨** — 기사 본문에 남의 API 토큰이 섞여 GitHub Push Protection에 걸린 것이다. unblock 대신 `news/core/redact.py`에 해당 토큰 패턴을 추가한다.

**Actions가 커밋에 실패** — Workflow permissions가 `Read and write`인지 확인한다.
