# EXEC_PLAN: spec-revamp

- **타입**: feat
- **프로젝트**: project/dev-news
- **상태**: IN_PROGRESS
- **생성일**: 2026-08-06T10:12:20.334Z

## 목표

SPEC.md의 Phase 1·2·3 구현 (1B 태그 도입은 범위 밖 — 데이터 누적 후 별도 세션).
무한 아카이브(월별 샤딩) + LLM 한도 대응(서킷 브레이커) + candidates 로그 +
요약 프롬프트 교체 + 고밀도 리스트 UI + 아카이브 검색 + 북마크 스냅샷.

## 접근법 (SPEC 대비 조정 사항)

- **SPEC 2.4의 "Pages가 data/를 정적 서빙" 가정은 틀림** — Pages 소스가 /docs 폴더라
  /data는 서빙 안 됨. 빌드가 `data/articles/*.json`·`search-index.json`을
  `docs/data/`로 복사해 해결. candidates 샤드는 서빙하지 않음(용량, 필요 시 추후).
- 1.3 재료 보강: enrich.py가 이미 GitHub README를 본문으로 수집 중 — 프롬프트 교체가 핵심.
- 1.5 Δ: github 스크래퍼의 upvotes가 이미 "stars today". candidates 로그의 전일 스냅샷과
  API 현재 스타 수로 Δ 계산, 첫 등장은 stars today 사용.
- 요약 "없음"(덧붙일 정보 없음) → summary 빈 문자열로 게시하되 UI에서 요약 줄 생략.
  LLM 미처리(한도)와 구분하기 위해 `llm_done` 플래그 도입 — 미처리 기사는 미게시·seen 미등록.

## 단계별 계획

1. Phase 2.1~2.3: archive.py 월별 샤드 재작성 + 멱등 마이그레이션 + seen 영구화 + 검색 인덱스
2. Phase 1: candidates.py 신설(GitHub API 메타·Δ), summarizer 서킷 브레이커·프롬프트 교체,
   build.py 깔때기 재구성, config 수집 확대(arXiv·r/LocalLLaMA)·llm.max_calls_per_run
3. Phase 3 + 2.4~2.5: template.html 고밀도 행(60~80px)·점수/썸네일/HOT 제거·NEW→점·
   체크박스 호버·상태카드 강등·아카이브 검색·보관함 스냅샷 마이그레이션
4. daily.yml에 GITHUB_TOKEN 전달
5. 테스트: 샤딩/마이그레이션 멱등, seen 영구, 429 mock 서킷 브레이커, 템플릿 회귀
6. 실데이터 마이그레이션 실행 + 재렌더 + verify → 커밋 → push

## 완료 기준

- 마이그레이션 후 기존 기사가 월별 샤드에 보존, articles.json 제거, 두 번 실행해도 안전
- 429 mock 테스트: 무한 재시도 없이 부분 결과로 exit 0, 미처리 기사 seen 미등록
- --demo / --no-ai 정상 동작, 깔때기 수치 로그 출력
- 1440px 뷰포트에 기사 10건 이상, 보관함·읽음·복사 정상
- 30일 지난 기사를 검색으로 찾아 상세 열람 가능
- pytest·린트 전체 통과
