# GitHub Actions로 운영하기

dev-news는 서버 없이 GitHub Actions와 GitHub Pages만으로 돈다.
워크플로 하나(`.github/workflows/daily.yml`)가 하루 세 번 수집해 결과를 저장소에 커밋하고, Pages가 `docs/` 폴더를 그대로 서빙한다.

```
cron (07·15·23 UTC)
  └─ checkout (전체 이력)
  └─ Python 3.12 + pip 캐시
  └─ python build.py          ← 수집·요약·렌더
  └─ git commit + pull --rebase + push   (docs/ · data/)
  └─ 실패 시 🔴 이슈 / 게시 급감 시 🟡 이슈
```

## 1. 처음 설정

### 1-1. 저장소 만들기

깃허브에서 빈 저장소를 만든다. **public**이어야 Pages가 무료다.

```bash
git init
git add .
git commit -m "첫 커밋"
git branch -M main
git remote add origin https://github.com/<아이디>/dev-news.git
git push -u origin main
```

### 1-2. 시크릿 등록

**Settings → Secrets and variables → Actions → Secrets → New repository secret**

| 이름 | 필수 | 발급처 |
|---|---|---|
| `GROQ_API_KEY` | 기본 공급자라 필수 | https://console.groq.com |
| `OPENROUTER_API_KEY` | `LLM_PROVIDER=openrouter`일 때만 | https://openrouter.ai |
| `GEMINI_API_KEY` | `LLM_PROVIDER=gemini`일 때만 | https://aistudio.google.com |

`GITHUB_TOKEN`은 등록하지 않는다. Actions가 자동으로 넣어 주며, GitHub API 한도를 시간당 60회에서 1,000회 이상으로 올리는 데 쓴다.

### 1-3. 변수 등록 (선택)

**Settings → Secrets and variables → Actions → Variables**

| 이름 | 기본값 | 용도 |
|---|---|---|
| `LLM_PROVIDER` | `groq` | 요약 공급자. `groq` · `openrouter` · `gemini` |
| `LLM_MODEL` | 공급자 기본 모델 | 모델 ID를 직접 지정. Groq가 모델을 폐기했을 때 코드 수정 없이 되돌리는 용도 |

시크릿과 달리 변수는 값이 로그에 보여도 되는 것만 넣는다.

### 1-4. 워크플로 권한

**Settings → Actions → General → Workflow permissions** 에서 **Read and write permissions** 를 고른다.

워크플로가 결과를 커밋하고 알림 이슈를 만들어야 하므로 `contents: write`와 `issues: write`가 필요하다.
이 설정이 Read only면 마지막 커밋 스텝에서 403으로 실패한다.

### 1-5. Pages 켜기

**Settings → Pages**

- Source: **Deploy from a branch**
- Branch: **main**, 폴더: **/docs**

저장하면 `https://<아이디>.github.io/dev-news/` 주소가 생긴다.
`docs/index.html`이 아직 없으면 404가 뜨는데, 첫 실행 뒤에 생긴다.

### 1-6. 첫 실행

**Actions 탭 → 매일 뉴스 수집 → Run workflow → Run workflow**

2~3분 걸린다. 끝나면 `뉴스 갱신 2026-09-02 21:01` 같은 커밋이 생기고, 1분쯤 뒤 Pages에 반영된다.

## 2. 스케줄

```yaml
schedule:
  - cron: "0 7,15,23 * * *"   # UTC
```

| UTC | KST |
|---|---|
| 07:00 | 16:00 |
| 15:00 | 00:00 |
| 23:00 | 08:00 |

- 무료 계정의 스케줄 실행은 러너가 붐비면 수십 분 밀린다. 정시가 중요하면 `50 6,14,22 * * *`처럼 앞당긴다.
- 저장소에 60일간 커밋이 없으면 GitHub가 스케줄을 자동으로 끈다. 이 프로젝트는 매 회차 커밋하므로 해당 없다.
- `concurrency: daily-news`로 같은 워크플로가 겹쳐 돌지 않는다. 앞 회차가 끝날 때까지 뒤 회차가 기다린다.
- `timeout-minutes: 25`를 넘기면 강제 종료된다. 평소 3분 안에 끝나므로 넘긴다면 어딘가 매달린 것이다.

## 3. 수동 실행

**항상 Run workflow 버튼을 쓴다.** 지난 실행 페이지의 **Re-run jobs**는 쓰지 않는다.

Re-run은 그 실행 시점의 커밋을 체크아웃해 돈다. 그 사이 다른 회차가 커밋을 쌓았으면 옛 코드·옛 데이터로 결과를 만들고, push 단계에서 원격이 앞서 있어 거부된다.
워크플로에 `git pull --rebase -X theirs` 방어가 있어 대부분 흡수되지만, 옛 코드로 돈 결과가 남는 것 자체가 문제다.

같은 날 여러 번 돌리면 매번 새 기사 20건이 추가된다. `seen.json`이 이미 실린 기사를 막으므로 중복은 없지만, 차순위 기사가 계속 쌓여 페이지가 부풀어진다.

## 4. 커밋 방식

워크플로는 `docs/`와 `data/`만 스테이징한다.

```
git add -A docs data
git commit -m "뉴스 갱신 $(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M')"
git pull --rebase -X theirs origin main
git push origin main
```

- 변경이 없으면 커밋을 건너뛴다.
- `pull --rebase -X theirs`는 충돌 시 방금 만든 데이터를 남긴다. 그래서 `fetch-depth: 0`으로 전체 이력을 받는다. 얕은 체크아웃이면 공통 조상을 못 찾아 rebase가 실패한다.
- 커밋 작성자는 `github-actions[bot]`이다.

로컬에서 코드를 고쳐 push할 때 Actions 커밋과 겹치면 로컬 쪽이 거부된다. `git pull --rebase` 후 다시 push하면 된다. `docs/index.html`이 충돌하면 어느 쪽이든 받고 `python scripts/retag.py`로 재생성하면 된다.

## 5. 알림

워크플로는 GitHub 이슈로 알린다. 같은 제목의 열린 이슈가 있으면 댓글로 붙이고, 없으면 새로 연다.
연속 실패가 이슈 하나의 타임라인이 되고, 고쳐서 닫으면 다음 실패에 새로 열린다.

| 이슈 | 조건 | 뜻 |
|---|---|---|
| 🔴 뉴스 수집 실패 | 어느 스텝이든 exit 1 | 수집·요약·커밋 중 하나가 깨졌다 |
| 🟡 게시 건수 급감 | 성공했지만 게시가 `alert.min_published`(기본 10건) 미만 | 요약 한도, 후보 고갈, 필터 과잉 등 조용한 열화 |

임계값은 `config.yaml`의 `alert.min_published`로 바꾼다.

## 6. 문제 해결

로그는 **Actions 탭 → 해당 실행 → build 잡**에서 본다.

### 커밋 스텝에서 push 거부 (GH013)

```
remote: error: GH013: Repository rule violations found for refs/heads/main.
remote: - Push cannot contain secrets
```

기사 본문에 남의 API 토큰(Hugging Face `hf_…`, OpenAI `sk-…` 등)이 섞여 GitHub Push Protection에 걸린 것이다. 그 회차 수집분은 통째로 유실된다.

**unblock URL로 허용하지 않는다.** `news/core/redact.py`에 해당 토큰 형식의 패턴을 추가해 마스킹한다.
테스트나 문서에 토큰처럼 보이는 문자열을 직접 쓰면 그 파일도 차단되므로 `"hf_" + "K" * 37`처럼 런타임에 조합한다.

### 커밋 스텝에서 403

Workflow permissions가 Read only다. 1-4를 확인한다.

### 요약이 전부 실패

로그에서 `[summarizer] groq · <모델>` 줄과 첫 번째 `오류(n/3): HTTP …` 줄을 본다.

| 오류 | 원인 | 조치 |
|---|---|---|
| `HTTP 401` | 키가 없거나 폐기됨 | 시크릿을 다시 등록한다 |
| `HTTP 429` | 무료 한도 초과 | 다음 회차에 자동 회수된다. 계속되면 `llm.pause_seconds`를 늘리거나 `max_calls_per_run`을 줄인다 |
| `model_decommissioned` | Groq가 모델을 폐기 | https://console.groq.com/docs/models 에서 현재 ID를 찾아 `LLM_MODEL` 변수에 넣는다 |

`[n/20] 실패 · <제목>` 줄의 뒷부분은 기사 제목이지 모델명이 아니다. AI 뉴스라 제목에 모델명이 흔해서 헷갈린다.

`[한도] … 한도 도달` 로그를 429로 단정하지 않는다. 401이 기사마다 재시도되며 예산을 태워도 같은 메시지가 찍힌다. 첫 `오류` 줄이 진짜 원인이다.

### 게시 0건인데 성공으로 끝남

🟡 이슈가 열린다. 로그에서 순서대로 확인한다.

1. `[summarizer]` 성공 건수 — 요약이 전부 실패하면 게시도 0이다
2. `[깔때기]` 후보 수 — 키워드·차단어 필터가 과하게 자르는지
3. `[seen]` 제외 건수 — 이미 소개한 기사가 많으면 후보가 마른다

### 특정 출처가 0건

- **긱뉴스** — RSS 주소가 바뀐 것이다. `news/scrapers/geeknews.py`의 `FEED_CANDIDATES`에 새 주소를 추가한다.
- **Reddit** — 러너 IP가 403으로 막힌다. `config.yaml`에서 `reddit: false`로 둔다. 공개 RSS 경로(`feeds`의 `r/LocalLLaMA/.rss`)는 별개다.
- **RSS 피드 하나** — 피드 하나가 죽어도 나머지는 계속 수집된다. 본문 추출 실패는 `data/fetch_health.json`에 원인별로 남는다.

### 스케줄이 안 돈다

- Actions 탭에서 워크플로가 disabled인지 본다. 저장소가 60일간 조용하면 GitHub가 끈다.
- fork한 저장소는 스케줄이 기본으로 꺼져 있다. Actions 탭에서 켠다.

### 로그를 API로 받기

gh CLI가 없는 환경에서는 REST API로 받는다. 익명 요청은 403이므로 토큰이 필요하다.

```bash
curl -L -H "Authorization: Bearer <토큰>" \
  https://api.github.com/repos/<아이디>/dev-news/actions/runs/<run_id>/logs -o logs.zip
```

## 7. 워크플로 수정할 때

- 스케줄을 바꾸면 UTC 기준임을 잊지 않는다.
- 새 시크릿을 쓰면 `수집 · 요약 · 페이지 생성` 스텝의 `env`에 추가해야 `build.py`가 읽는다.
- `git add -A docs data` 범위를 넓히면 `.env`나 캐시가 커밋될 수 있다. `.gitignore`를 같이 확인한다.
- 알림 문구는 `scripts/notify.sh`가 아니라 워크플로의 `실패 알림` · `열화 알림` 스텝에 있다.
