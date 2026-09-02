[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/dakcoe/dev-news/pulls)

# dev-news

매일 00시·08시·16시(KST)에 개발·AI 뉴스를 수집해 정적 페이지 한 장으로 만들어 두는 도구.
GitHub Actions에서 돌면 서버가 필요 없고, `python build.py` 한 줄로 로컬에서도 똑같이 돌아간다.

**보기:** https://dakcoe.github.io/dev-news/

## 파이프라인

```
수집 → 필터 → 점수화 → 중복 제거 → 본문 추출 → LLM 요약 → 태그 → 월별 저장 → docs/index.html
```

| 단계 | 하는 일 | 코드 |
|---|---|---|
| 수집 | HN · GitHub Trending · Lobste.rs · dev.to · 긱뉴스 · RSS · Anthropic | `news/scrapers/` |
| 필터 | 키워드 화이트리스트 · 비개발 주제 차단어 · 발행 시간 창 | `news/core/filters.py` |
| 점수화 | 업보트·댓글·교차 출처·시간 감쇠. 화면에는 안 보이고 선별에만 쓴다 | `news/core/scorer.py` |
| 중복 제거 | URL 정규화 + 제목 유사도, 한 번 실린 URL은 `seen.json`으로 영구 차단 | `news/core/dedup.py` · `seen.py` |
| 선별 | 출처별 상한 · 예약석(quota) · 회차당 `top_n`건 | `news/core/select.py` |
| 본문 추출 | trafilatura로 본문·OG 메타 추출 | `news/core/enrich.py` |
| 요약 | Groq(기본) · OpenRouter · Gemini. 실행당 호출 예산 있음 | `news/summarizer.py` |
| 태그 | 닫힌 어휘 20개, 규칙 매칭. LLM 자유 태그 없음 | `news/core/tags.py` |
| 저장 | 월별 샤드 + 검색 색인 + 후보 로그 | `news/core/archive.py` · `candidates.py` |
| 렌더 | 템플릿 하나에 최근 30일 기사를 구워 넣는다 | `news/render.py` · `template.html` |

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
data/
  articles/YYYY-MM.json # 실린 기사. 지난 달 샤드는 불변
  candidates/YYYY-MM.json
  search-index.json     # 아카이브 검색용 경량 색인
  seen.json             # 한 번 실린 URL
docs/                   # GitHub Pages 루트 — index.html + data/ 서빙 사본
scripts/                # retag(소급 태깅) · eval_summary(요약 채점) · notify(이슈 알림)
tests/                  # pytest
.github/workflows/daily.yml
```

## 로컬 실행

```bash
pip install -r requirements.txt
python build.py --demo     # 레이아웃만, 네트워크·키 불필요
python build.py --no-ai    # 실제 수집, 요약 없음
python build.py            # 전체 실행 — .env에 GROQ_API_KEY 필요
```

`.env.example`을 `.env`로 복사해 키를 채운다. 결과는 `docs/index.html`.

## 문서

- [GitHub Actions로 운영하기](GITHUB_ACTIONS.md) — Pages 설정, 시크릿·변수, 스케줄, 알림, 문제 해결
- [설정 가이드](CONFIG.md) — 수집 소스, 선별·점수, 요약 모델, 태그, 저장 구조, 페이지 사용법
- [개편 스펙](SPEC.md) — 설계 배경과 하지 말 것

## 개발

```bash
python -m pytest -q
python -m ruff check .
```
