# EXEC_PLAN: page-design-tweaks

- **타입**: feat
- **프로젝트**: project/dev-news
- **상태**: COMPLETED
- **생성일**: 2026-08-05T18:14:27.375Z

## 목표

뉴스 페이지 UI를 사용자 요청대로 다듬는다: (1) 상태 카드의 "뉴스 수집" 가짜 버튼 제거,
(2) 왼쪽 레일 버튼 확대, (3) 기사 상세 패널이 열릴 때 왼쪽 목록을 흐리게 만드는
오버레이 제거 — 목록이 선명하게 유지되고 열린 채로 다른 기사를 바로 클릭할 수 있게.

## 접근법

페이지 전체가 `news/template.html` 단일 파일(CSS+JS 인라인)이므로 그 파일만 수정한다.
design 워크스페이스의 refinement-directives 원칙(요청받은 축만 좁게 수정, 전체 재작성 금지)을 따른다.

- 뉴스 수집 버튼: `.stbtn` 요소·CSS·전용 아이콘(`I.rf`) 제거, 통계(`stmeta`)는 유지
- 레일 버튼: `.rail` 62→74px, `.rb` 40→50px, 아이콘 21→25px
- 오버레이: `.ov` 요소·CSS·open/close 호출 제거. 닫기는 ✕ 버튼과 Esc로 유지,
  선택된 행은 `.row.act` 테두리로 표시되므로 맥락은 유지된다

## 단계별 계획

1. `news/template.html` 수정 (버튼 제거 → 레일 확대 → 오버레이 제거)
2. pytest 테스트 작성: sample.json으로 렌더한 HTML에 stbtn/오버레이가 없고 레일 크기가 반영됐는지 검증
3. `python build.py --demo`로 로컬 렌더 확인
4. `node scripts/verify-task.js` 통과 → 커밋 → push → complete-task

## 완료 기준

- 렌더된 페이지에 "뉴스 수집" 버튼과 `.ov` 오버레이가 없다
- 레일 버튼이 50px로 커졌다
- 기사 상세를 열어도 왼쪽 목록이 흐려지지 않고 클릭 가능하다
- pytest 테스트 통과, verify-task.js 통과
- **완료일**: 2026-08-05T18:19:05.978Z
