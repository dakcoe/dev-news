[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/dakcoe/dev-news/pulls)

# dev-news

매일 세 번(00·08·16시 KST) 개발·AI 뉴스를 수집해 한국어로 요약하고 정적 페이지 한 장으로 만들어 두는 도구.
GitHub Actions에서 돌면 서버가 필요 없고, `python build.py` 한 줄로 로컬에서도 똑같이 돌아간다.

**보기:** https://dev-news.net/

## 파이프라인

```
수집 → 필터 → 점수화 → 중복 제거 → 본문 추출 → LLM 요약 → 태그 → 월별 저장 → docs/index.html
```

| 단계 | 하는 일 | 코드 |
|---|---|---|
| 수집 | HN · GitHub Trending · Lobste.rs · dev.to · 긱뉴스 · RSS · Anthropic | `news/scrapers/` |
| 필터 | 닫힌 차단 목록(제목만 판정) · 발행 시간 창. 선별된 출처는 화이트리스트를 거치지 않는다 | `news/core/filters.py` |
| 점수화 | 업보트·댓글·교차 출처·시간 감쇠. 화면에는 안 보이고 선별에만 쓴다 | `news/core/scorer.py` |
| 중복 제거 | URL 정규화 + 제목 유사도, 한 번 실린 URL은 `seen.json`으로 영구 차단 | `news/core/dedup.py` · `seen.py` |
| 선별 | 출처별 상한 · 예약석(quota) · 회차당 `top_n`건 | `news/core/select.py` |
| 본문 추출 | trafilatura로 본문·OG 메타 추출 | `news/core/enrich.py` |
| 요약 | Groq(기본) · OpenRouter · Gemini. 실행당 호출 예산 있음 | `news/summarizer.py` |
| 태그 | 닫힌 어휘 20개, 규칙 매칭. LLM 자유 태그 없음 | `news/core/tags.py` |
| 저장 | 월별 샤드 + 월별 검색 색인 + 후보 로그 | `news/core/archive.py` · `candidates.py` |
| 렌더 | 템플릿 하나에 최근 30일 기사를 구워 넣는다. SEO 파일(sitemap·robots·llms.txt)도 여기서 | `news/render.py` · `template.html` |

기사와 별개로 무료 API 카탈로그(`news/apis_catalog.py`)를 매 회차 다시 파싱해 `docs/data/apis.json`으로 내보낸다.

## 디렉터리

```
build.py                # 진입점. --demo(샘플 렌더) · --no-ai(요약 생략)
config.yaml             # 수집·선별·요약·알림 설정 전부
news/
  scrapers/             # 출처별 수집기
  core/                 # 필터·점수·중복·선별·태그·저장
  summarizer.py         # LLM 요약
  render.py · template.html
  apis_catalog.py · api_health.py
docs/                   # GitHub Pages 루트. 페이지와 기사 정본이 여기 있다
  index.html
  data/articles/YYYY-MM.json   # 실린 기사. 지난 달 샤드는 불변
  data/search-index.json       # 달 목록. 색인 본체는 search-index-YYYY-MM.json
  data/apis.json               # 무료 API 카탈로그
data/
  seen.json             # 한 번 실린 URL. 기사를 지우면 여기서도 빼야 다시 올라온다
  candidates/YYYY-MM.json
  *_health.json         # 출처·본문 추출·API 링크 상태
scripts/                # publish(수집·커밋·푸시) · 소급 태깅 · 요약 채점 · 회차 합치기 · 이슈 알림
tests/                  # pytest
.github/workflows/
  daily.yml             # 수집 파이프라인 — 수동 실행 전용 (비상용)
  watchdog.yml          # 10시간 넘게 갱신 커밋이 없으면 이슈를 연다
```

## 로컬 실행

```bash
pip install -r requirements.txt
python build.py --demo     # 레이아웃만, 네트워크·키 불필요
python build.py --no-ai    # 실제 수집, 요약 없음
python build.py            # 전체 실행 — .env에 GROQ_API_KEY 필요
```

`.env.example`을 `.env`로 복사해 키를 채운다. 결과는 `docs/index.html`.

화면만 고쳤을 때는 수집을 다시 돌리지 않는다. 저장된 기사를 읽어 `render()`만 부르면
수집도 LLM 호출도 없다.

## 실행 방식

수집은 자기 기계에서 `scripts/publish.sh`를 정각(00·08·16시 KST)에 돌려 커밋·푸시한다.
GitHub Pages가 `docs/`를 그대로 서빙한다. Actions는 두 가지만 한다 — `watchdog.yml`이
10시간 넘게 갱신이 없으면 이슈를 열고, `daily.yml`은 손으로 한 번 돌리는 비상용이다.

Actions에서 수집을 돌리지 않는 이유는 둘이다. 러너의 IP를 여러 사이트가 막아 본문 추출이
8% 실패했고(같은 주소가 집에서는 멀쩡히 받아진다), 예약 실행이 실측으로 2~5시간 늦게
시작했다. 자세한 것은 [GITHUB_ACTIONS.md](GITHUB_ACTIONS.md) 2절.

## 문서

- [GitHub Actions로 운영하기](GITHUB_ACTIONS.md) — Pages 설정, 시크릿·변수, 스케줄, 알림, 문제 해결
- [설정 가이드](CONFIG.md) — 수집 소스, 선별·점수, 요약 모델, 태그, 저장 구조, 페이지 사용법
- [개편 스펙](SPEC.md) — 설계 배경과 하지 말 것

## 개발

```bash
python -m pytest -q      # 500여 건. 1초 안에 끝난다
```

수집·요약을 건드렸으면 `python build.py --no-ai`로 실제 출처까지 한 번 돌려 본다.
결과 파일은 커밋하지 않고 `git checkout -- docs data`로 되돌린다.
