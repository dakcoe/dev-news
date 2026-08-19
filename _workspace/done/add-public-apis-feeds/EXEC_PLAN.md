# EXEC_PLAN: add-public-apis-feeds

- **타입**: feat
- **프로젝트**: project/dev-news
- **상태**: COMPLETED
- **생성일**: 2026-08-19T20:04:26.651Z

## 목표

public-apis(본가)·public-apis-4Kr(한국판)의 **전체 API 목록**을 카탈로그로 보여주는
API 뷰를 왼쪽 레일에 추가한다. 매 수집 회차(하루 3회)마다 README를 다시 긁어
목록 전체를 갱신한다.

## 접근법 (1차 시도에서 방향 전환)

- ~~1차: 커밋 Atom 피드를 `api` 소스로 수집~~ → **폐기**. 커밋 피드는 "앞으로
  추가되는 것"만 잡히고 이미 등록된 1,400여 개는 안 보인다 (사용자 피드백).
- **2차(확정): README 전체 파싱 방식.** 두 리포의 raw README를 받아 `### 카테고리`
  아래 마크다운 표를 파싱 → `docs/data/apis.json` 스냅샷 생성. 뉴스 기사
  파이프라인(요약·seen·아카이브)과 완전히 분리 — 기사 아님, LLM 예산 0.
  - 스폰서 표 배제: 목차 헤딩(`## Index`/`## 목차`) 이후의 카테고리만 수집.
  - 갱신: build.py 말미에 sync — 네트워크 실패 시 기존 파일 유지(회차 안 죽임).
- **템플릿**: 레일 API 버튼 유지. API 뷰는 첫 진입 때 apis.json을 지연 fetch
  (아카이브 샤드와 같은 패턴), 검색 + 출처(본가/한국판) + 카테고리 필터 제공.
  IME 유지를 위해 목록 컨테이너만 부분 갱신.
- **1차 작업분 되돌리기**: rss.py source/title_skip, config api 피드·점수·창,
  TRUSTED api, SOURCE_META api, sample.json api 항목, 뷰 스코프(inView) 전부 원복.

## 단계별 계획

1. 1차 작업분 되돌리기 (rss.py · config.yaml · build.py · render.py · sample.json · template 스코프)
2. `news/apis_catalog.py` — README 파서 + sync (테스트 먼저: 픽스처 md, 실패 내성)
3. build.py — 회차 말미에 apis_catalog.sync 호출
4. template.html — API 뷰를 카탈로그 렌더링으로 교체 (지연 fetch · 검색 · 필터)
5. docs/index.html 동일 패치 + docs/data/apis.json 1회 생성 (즉시 라이브 반영)
6. node scripts/verify-task.js → 커밋 → complete-task.js

## 완료 기준

- pytest 전체 통과 (신규: 파서가 두 형식 표를 다 읽음, 목차 이전 스폰서 표 배제,
  네트워크 실패 시 기존 파일 유지, 렌더 출력에 API 레일 버튼·카탈로그 뷰)
- 데모 페이지에서 API 뷰 진입 → 카탈로그 표시·검색·필터 동작 (브라우저 실측)
- 뉴스 뷰는 변경 전과 동일 동작
- **완료일**: 2026-08-19T20:19:57.580Z
