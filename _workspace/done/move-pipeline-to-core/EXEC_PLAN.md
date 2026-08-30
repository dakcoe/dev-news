# EXEC_PLAN: move-pipeline-to-core

- **타입**: refactor
- **프로젝트**: project/dev-news
- **상태**: COMPLETED

## 목표

`build.py`가 진입점이면서 동시에 파이프라인 라이브러리다. 545줄에 함수 17개인데
그중 절반이 `news/core/`에 있어야 자연스러운 것들이다.

  keyword_filter · _keyword_re · _block_re · recent_only · page_eligible
  drop_dead_links · drop_irrelevant · pick · adjust_scores · dedupe

증거는 import 방향이다 — 테스트 7개와 스크립트 2개가 `from build import ...`로
파이프라인 함수를 가져다 쓴다. 진입점에서 로직을 꺼내 쓰고 있다는 뜻이다.
`dedupe`는 이미 `news/core/dedup.py`로 위임하는 껍데기만 남아 있다.

## 접근법

성격에 따라 두 모듈로 나눈다.

  news/core/filters.py   무엇을 버릴지 — keyword_filter · recent_only ·
                         page_eligible · drop_dead_links · drop_irrelevant
                         + TRUSTED · _keyword_re · _block_re
  news/core/select.py    무엇을 실을지 — adjust_scores · pick

`build.py`에는 오케스트레이션만 남긴다 — load_dotenv · load_config ·
run_scrapers · apply_star_delta · emit_actions_output · sync_docs_data · main.

**재노출 shim을 두지 않는다.** `from build import keyword_filter`가 계속
동작하게 만들면 build.py는 여전히 라이브러리다. 호출부(테스트 7개 · 스크립트
2개)를 새 경로로 고친다 — 테스트가 우리 것이라 고칠 수 있고, 334개 테스트가
동작을 잡아 준다.

**껍데기 `dedupe`는 지운다.** `merge_duplicates`를 main에서 직접 부른다.

## 위험

이번 단계가 가장 위험하다. 순수 이동이지만 import 경로가 9개 파일에서 바뀐다.
순환 import에 주의한다 — `filters`가 `summarizer.IRRELEVANT`를 쓰는데
summarizer는 build를 참조하지 않으므로 안전하다.

## 단계별 계획

1. `news/core/filters.py` · `news/core/select.py` 신설, 함수 이동
2. `build.py` 정리 — 이동한 함수 제거, import 갱신, dedupe 껍데기 삭제
3. 호출부 갱신 — 테스트 7개 · `scripts/retag.py` 등
4. 로컬 전체 실행으로 결과가 이전 회차와 같은지 확인
5. `node scripts/verify-task.js` → 커밋 → `complete-task.js`

## 완료 기준

- `build.py`가 300줄 아래로 내려간다
- 파이프라인 함수가 `news/core/`에 있다
- `from build import` 로 파이프라인 함수를 가져가는 곳이 없다
- 로컬 전체 실행 결과(수집·선별 건수)가 직전 회차와 같다
- 334개 테스트 전부 통과

## 결과 (2026-08-31)

  build.py            545 → 295줄
  news/core/filters.py      182줄 (신설)
  news/core/select.py        90줄 (신설)

`from build import`로 파이프라인 함수를 가져가던 곳이 사라졌다. 남은 것은
오케스트레이션 함수뿐이다 — `emit_actions_output`(test_alert) ·
`load_dotenv`(fix_hanja) · `load_config, sync_docs_data`(retag).

껍데기만 남아 있던 `dedupe`는 지우고 `merge_duplicates`를 main에서 직접 부른다.

**순수 이동임을 로컬 전체 실행으로 확인했다.** 직전 회차와 숫자가 완전히 같다.

  후보 240건 → 필터·중복 제거 후 142건 → 미소개 95건 → 최종 선별 19건
  [선별] devto 4 · geeknews 5 · github 4 · hackernews 5 · rss 1
  [enrich] 본문 18/19 · 썸네일 17/19

334개 테스트 통과. 순환 import는 없었다 — filters가 summarizer.IRRELEVANT를
쓰지만 summarizer는 build를 참조하지 않는다.
- **완료일**: 2026-08-30T19:05:08.070Z
