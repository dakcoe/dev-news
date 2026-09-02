[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/dakcoe/dev-news/pulls)

# dev-news

매일 00시·08시·16시(KST)에 개발·AI 뉴스를 수집해 정적 페이지 한 장으로 만들어 두는 도구.
GitHub Actions에서 돌면 서버가 필요 없고, `python build.py` 한 줄로 로컬에서도 똑같이 돌아간다.

수집 → 필터 → 점수화 → 중복제거 → 본문·썸네일 추출 → LLM 요약 → `docs/index.html` 생성.

## 수집 소스

| 소스 | 방식 |
|---|---|
| Hacker News | Firebase API `topstories` 상위 N개 |
| GitHub Trending | `github.com/trending` 일간 |
| Lobste.rs | `hottest.json` |
| dev.to | 태그별 rising 글 |
| 긱뉴스 | `news.hada.io` RSS |
| RSS 피드 | `config.yaml`의 `feeds`에 적은 주소 전부 |
| Anthropic | `anthropic.com/news` · `/engineering` HTML 직접 파싱 (RSS 미제공) |
| Reddit | 서브레딧 (기본 꺼짐 — 아래 참고) |

`config.yaml`의 `sources`에서 개별로 끄고 켠다.

### RSS 피드 추가

주소만 적으면 소스가 늘어난다.

```yaml
feeds:
  - name: Anthropic
    url: https://www.anthropic.com/news/rss.xml
  - name: 카카오 기술블로그
    url: https://tech.kakao.com/feed/
```

`name`을 생략하면 도메인이 출처 이름이 된다. 피드 하나가 죽어도 나머지는 계속 수집한다.

### Reddit이 기본으로 꺼져 있는 이유

비인증 `hot.json` 요청이 집 IP에서도 403(Blocked)으로 막힌다. 쓰려면 무료 앱을 만들어 인증을 붙여야 한다.

1. https://www.reddit.com/prefs/apps → create app → 타입 **script**
2. `.env`에 추가

   ```
   REDDIT_CLIENT_ID=앱_이름_아래_문자열
   REDDIT_CLIENT_SECRET=secret값
   ```

3. `config.yaml`에서 `reddit: true`

키가 없으면 공개 RSS로 한 번 더 시도하고, 그것도 막히면 그 소스만 건너뛴다.

## 빠른 시작 (로컬)

```bash
pip install -r requirements.txt

# 레이아웃만 확인 — 네트워크도 API 키도 필요 없음
python build.py --demo

# 실제 수집 (요약 없이, 키 불필요)
python build.py --no-ai
```

전체 실행에는 키가 필요하다. `.env.example`을 복사해 `.env`로 이름을 바꾸고 키를 채우면 끝이다.
셸에서 환경변수를 export 할 필요가 없다.

```powershell
copy .env.example .env      # 윈도우 (맥/리눅스는 cp)
notepad .env                # GROQ_API_KEY=gsk_... 채우기
python build.py
```

`.env`는 `.gitignore`에 들어 있어 깃허브에 올라가지 않는다.
이미 셸에 환경변수가 설정돼 있으면 그쪽이 우선이고, GitHub Actions에서는 Secrets가 쓰인다.

결과는 `docs/index.html`. 브라우저로 그냥 열면 된다.

## GitHub Pages에 올리기

1. 깃허브에서 빈 저장소 `dev-news`를 만든다 (public — Pages 무료 조건)

2. 이 폴더를 올린다

   ```bash
   cd dev-news
   git init
   git add .
   git commit -m "첫 커밋"
   git branch -M main
   git remote add origin https://github.com/<아이디>/dev-news.git
   git push -u origin main
   ```

3. **Settings → Secrets and variables → Actions → New repository secret**
   - 이름 `GROQ_API_KEY`, 값은 https://console.groq.com 에서 발급한 키

4. **Settings → Pages**
   - Source: `Deploy from a branch`
   - Branch: `main` / 폴더: `/docs` → Save

5. **Actions 탭 → 매일 뉴스 수집 → Run workflow** 로 한 번 수동 실행

   2~3분 뒤 `https://<아이디>.github.io/dev-news/` 로 접속된다.
   이후로는 매일 15:00 · 23:00 · 07:00 UTC(= 00시 · 08시 · 16시 KST) 하루 세 번 자동 실행된다.

> 깃허브 무료 계정의 스케줄 실행은 러너가 붐빌 때 최대 수십 분 밀릴 수 있다. 정시 도착이 중요하면 cron을 `50 6,14,22 * * *`처럼 조금 앞당겨 두면 된다.

## 요약 모델 바꾸기

환경변수 하나로 공급자를 바꾼다. Actions에서는 **Settings → Variables**에 `LLM_PROVIDER`를 넣으면 된다.

| `LLM_PROVIDER` | 필요한 키 | 무료 한도 | 비고 |
|---|---|---|---|
| `groq` (기본) | `GROQ_API_KEY` | 하루 1,000회 / 분당 30회 | 카드 등록 없음. 기본 모델 `llama-3.3-70b-versatile` |
| `openrouter` | `OPENROUTER_API_KEY` | 하루 50회 | 크레딧 $10 넣으면 1,000회 |
| `gemini` | `GEMINI_API_KEY` | AI Studio 대시보드에서 확인 | 한국어 품질이 가장 좋음. `requirements.txt`의 `google-genai` 주석 해제 필요 |

모델만 바꾸려면 `LLM_MODEL` 변수를 지정한다. Groq는 모델을 종종 정리(deprecate)하므로,
실패 로그에 `model_decommissioned`가 보이면 https://console.groq.com/docs/models 에서 현재 모델 ID를 확인해 `LLM_MODEL`에 넣으면 된다.

## 설정 (`config.yaml`)

```yaml
scraper:
  top_n: 20          # 페이지에 올릴 최대 기사 수
  per_source: 5      # 한 출처가 차지할 최대 개수
  window_hours: 48   # 최근 몇 시간 내 발행분만
```

`keywords`는 제목·설명에 하나도 걸리지 않으면 버리는 화이트리스트다.
`github` / `devto` / `geeknews`는 이미 개발 전용 소스라 이 필터를 건너뛴다.

## 점수와 순서

```
기본점수 = 업보트 × 1.0 + 댓글 × 1.5 + 교차출처수 × 300
시간감쇠 = 8시간 이내 ×2.0 / 24시간 ×1.0 / 7일 ×0.5 / 그 이상 ×0.05
최종점수 = (기본점수 × 시간감쇠 + source_base) × source_weight
```

출처마다 숫자의 단위가 다르다. GitHub는 "오늘 받은 스타"라 수천 단위, HN은 수백 단위,
공식 블로그·긱뉴스는 아예 점수가 없다. 그대로 두면 GitHub가 상위를 독식하고 블로그 글은 바닥에 깔린다.
그래서 `config.yaml`에서 두 개의 손잡이를 준다.

```yaml
source_base:       # 점수 개념이 없는 출처의 바닥값
  anthropic: 900
  rss: 420
source_weight:     # 과대·과소평가 보정 배수
  github: 0.35
```

앤트로픽 글이 자꾸 밀리면 `source_base.anthropic`을 올리고, GitHub가 너무 많으면 `source_weight.github`을 낮추면 된다.

**자리 보장(quota)** — 점수와 무관하게 특정 출처의 자리를 먼저 확보한다.

```yaml
source_quota:
  github: 5        # 점수가 낮아도 GitHub 트렌딩 5건은 무조건 들어간다
```

선별은 두 단계다. ① quota에 적힌 출처를 각자 점수순으로 먼저 채우고, ② 남은 자리를 전체 점수순으로 채우되 `per_source` 상한을 지킨다.
후보가 모자라면 확보한 만큼만 들어가고 `[선별] github 보장 5건 중 3건만 확보` 같은 로그가 남는다.

## 누적과 중복 제거

페이지는 매일 갈아엎지 않고 **회차별로 쌓인다.** 디스코드 포럼에서 "8월 5일 09시 뉴스 목록"이 위에 붙는 것과 같은 방식이다.

- `data/articles.json` — 지금까지 실린 기사 전부. 매 실행마다 새 기사가 맨 앞에 붙는다
- `data/seen.json` — 한 번 소개한 URL을 30일 기억. 같은 기사가 두 번 실리지 않는다

두 파일 모두 Actions가 저장소에 커밋하므로, 실행 환경이 매번 초기화돼도 누적이 유지된다.

```yaml
scraper:
  top_n: 20        # 한 회차에 새로 추가할 기사 수
  keep_days: 30    # 페이지에 남겨둘 기간
  max_items: 300   # 누적 상한. 넘으면 오래된 것부터 잘라낸다
```

페이지 상단 정렬에서 **수집순**을 고르면 회차 구분선이 보이고, 점수순·최신순·출처별로 바꾸면 회차를 무시하고 전체를 한 줄로 정렬한다.

> 로컬에서 압축을 다시 풀 때 `data/` 폴더는 덮어쓰지 말 것. 누적 기록이 거기 있다.
> (배포한 zip에는 이 파일들을 넣지 않았다)

## 페이지 사용법

- 좌측 레일: **오늘의 뉴스 / 보관함 / 수집 소스**
- 정렬: 점수순 · 최신순 · 출처별, 그리고 출처 태그로 필터
- 체크박스로 보관함에 담고, 보관함에서 **마크다운으로 복사** 가능
- 제목이나 우측 문서 아이콘을 누르면 번역 요약이 오른쪽 패널에 열린다
- `NEW`는 26시간 내 발행, `HOT`은 300점 이상

### 보관함과 읽음 표시

- **보관함** — 체크박스로 담는다. 좌측 레일의 북마크 아이콘에서 모아 보고, 마크다운으로 복사할 수 있다
- **읽음** — 상세를 열거나 원문을 열면 자동으로 읽음 처리되어 제목이 회색으로 흐려진다. 눈 아이콘으로 직접 켜고 끌 수 있고, 상단 `안 읽음` 필터로 미처 읽지 못한 기사만 모을 수 있다

둘 다 브라우저 로컬 저장소(`dev-news-saved`, `dev-news-read`)에 URL로 저장된다.
따라서 **페이지가 매일 새로 생성돼도 표시는 유지되고**, 30일이 지나 목록에서 빠진 기사도 다시 등장하면 읽음 상태가 그대로다.

기기·브라우저마다 따로 관리된다는 점만 유의. 집 PC와 폰을 동기화하려면 별도 저장소(백엔드나 Gist API)가 필요한데, 그 정도 규모는 아니라고 판단했다.

## 문제가 생기면

**긱뉴스가 0건** — RSS 주소가 바뀐 것이다. `news/scrapers/geeknews.py`의 `FEED_CANDIDATES`에 새 주소를 추가한다.

**Reddit이 403** — 깃허브 러너 IP가 차단된 경우다. `config.yaml`에서 `reddit: false`로 끄거나, Reddit OAuth 앱을 만들어 인증 방식으로 바꿔야 한다.

**요약이 전부 실패** — 키 이름이 공급자와 맞는지, Groq 모델 ID가 살아 있는지 확인한다. `--no-ai`로 돌리면 요약 없이도 페이지는 나온다.

**Actions가 커밋에 실패** — Settings → Actions → General → Workflow permissions를 `Read and write`로.
