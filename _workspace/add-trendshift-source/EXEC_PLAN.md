# EXEC_PLAN: add-trendshift-source

- **타입**: feat
- **프로젝트**: project/dev-news
- **상태**: IN_PROGRESS

## 목표

Trendshift(trendshift.io) 일간 순위를 수집 소스로 추가한다. GitHub 트렌딩과 같은 저장소가 오르면
중복 제거에서 하나로 합쳐지고 교차 출처 가산(+300)을 받는다.

OSS Insight는 제외 — `/v1/trends/repos` API가 2026-03-01부터 data_quality=unavailable로 빈 결과만 돌려준다
(이벤트 수집률 0.3%). 실측 2026-09-05.

## 접근법

- Trendshift는 `/api/`가 robots.txt로 금지돼 있고 홈페이지가 SSR HTML이다. 홈페이지의 "Trending // Daily"
  카드 25건을 파싱한다. 카드 = `/repositories/<id>` 링크(owner/repo) + 별 수 span + `<p>` 설명 + Like 버튼.
  "Live // Mentions" 블록에도 같은 링크가 있는데 Like 버튼이 없어 그걸로 구분한다.
- 아이템은 `source: "github"`, `feed: "Trendshift"`로 만든다. 이유:
  - 같은 저장소 URL이라 dedup 1단(URL 정규화)에서 GitHub 트렌딩 항목과 합쳐진다.
  - `apply_star_delta`, `candidates.github_meta`, 예약석 `source_quota.github`, 화면의 Δ 표시가 그대로 적용된다.
  - 화면 출처 라벨은 `from`(feed)이 있으면 그걸 쓰므로 "Trendshift"로 보인다.
  - 별도 source로 만들면 위 5곳을 전부 분기해야 한다.
- 켜고 끄기는 `config.yaml sources.trendshift`.

## 단계별 계획

1. `tests/test_trendshift.py` — 합성 HTML 픽스처로 parse(): 카드 25건 중 mentions 제외, 이름·URL·설명·별 수, 콤마 숫자, 배지 노이즈 제외, 빈 HTML → [] (RED)
2. `news/scrapers/trendshift.py` — parse(html) + fetch(limit)
3. `build.py run_scrapers`에 sources.trendshift 연결, `config.yaml sources`에 추가
4. `render.py SOURCE_META.github.desc`에 Trendshift 언급, `CONFIG.md` 소스 표에 행 추가
5. verify-task → 로컬 `--no-ai`로 실수집 확인 → 커밋

## 완료 기준

- pytest 전체 통과
- `python build.py --no-ai` 로그에 `[trendshift] N개 수집`이 찍히고, GitHub 트렌딩과 겹치는 저장소가 한 건으로 합쳐짐(merged_sources 확인)
