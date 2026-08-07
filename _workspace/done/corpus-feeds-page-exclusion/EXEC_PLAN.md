# EXEC_PLAN: corpus-feeds-page-exclusion

- **타입**: fix
- **프로젝트**: project/dev-news
- **상태**: COMPLETED
- **생성일**: 2026-08-07T22:01:09.036Z

## 목표

코퍼스 축적용 피드(r/LocalLLaMA, arXiv cs.AI/cs.CL)의 글이 페이지에 실리지 않게 한다.
8/7 배치에서 r/LocalLLaMA의 "Friday humor" 밈 게시물이 rss 기본점수 420을 업고
1020점으로 페이지에 게시된 것이 계기. SPEC 1.2가 명시한 이 피드들의 목적은
"1B 태그 어휘 도출용 코퍼스 축적"이며 페이지 게재가 아니다.

## 접근법

피드별 `page: false` 플래그 도입 (candidates 기록은 유지, 페이지 선별만 제외).

- SPEC 1.1 "후보를 넓게 기록하는 것과 페이지에 뭘 싣는가는 별개다"와 정합 —
  파이프라인 차단 필터가 아니라 페이지 게재 자격의 구분이다.
- candidates 로그는 전 후보(코퍼스 피드 포함)를 그대로 기록하므로 1B 재료 축적 무손실.
- 키워드 필터 방식(대안)은 밈 제목에 우연히 키워드가 들어가면 뚫리고, 정상 글이
  키워드가 없으면 잘리는 양방향 오류가 있어 배제.

## 단계별 계획

1. RED — 테스트 작성: (a) rss 스크래퍼가 feed의 `page: false`를 아이템에 전파,
   (b) 기본값은 `page: true`(기존 피드 무영향), (c) build 파이프라인이 `page: false`
   아이템을 페이지 선별에서 제외하되 candidates 로그에는 포함.
2. GREEN — `news/scrapers/rss.py`: `_one()`에서 `feed.get("page", True)`를
   아이템의 `page` 필드로 전파.
3. GREEN — `build.py`: `pick()` 호출 전에 `page` False 아이템을 제외하고 제외 건수를
   로그. `candidates.log()`는 기존대로 전체 목록을 받으므로 변경 없음.
4. `config.yaml`: arXiv cs.AI · arXiv cs.CL · r/LocalLLaMA 피드에 `page: false` 추가,
   주석으로 사유 명기.
5. 검증 — `node scripts/verify-task.js project/dev-news` (pytest + ruff).

## 완료 기준

- 신규 테스트 3건 포함 전체 pytest 통과, ruff 통과.
- `page: false` 피드의 아이템이 pick 대상에서 빠지고 candidates 로그에는 남는 것이
  테스트로 확인됨.
- 기존 피드(공식 블로그 등)는 동작 변화 없음 (기본값 `page: true`).
- **완료일**: 2026-08-07T22:04:03.044Z
