# EXEC_PLAN: unread-toggle-checkbox

- **타입**: feat
- **프로젝트**: project/dev-news
- **상태**: COMPLETED
- **생성일**: 2026-08-05T18:25:08.196Z

## 목표

(1) 필터 바의 "안 읽음" 토글 버튼에 체크박스 표시를 넣어 켜짐/꺼짐 상태가 한눈에 보이게 한다.
(2) 토글 시 목록 길이가 바뀌며 스크롤바가 나타났다 사라져 화면 전체가 좌우로 밀리는 레이아웃 시프트를 고친다.

## 접근법

`news/template.html`만 수정.

- 체크박스: `#unread` 칩의 눈 아이콘을 작은 체크박스(`.ckm`)로 교체 — 꺼짐이면 빈 테두리 박스,
  켜짐이면 보라색 채움 + 흰 체크 (기사 행의 보관 체크박스 `.ck`와 같은 문법이라 일관적)
- 레이아웃 시프트: `.scroll`에 `scrollbar-gutter:stable` 추가 — 스크롤바 유무와 무관하게 폭 고정

## 단계별 계획

1. template.html 수정 (ckm CSS + barHTML 교체 + scrollbar-gutter)
2. tests/test_template.py에 회귀 테스트 2개 추가
3. data/articles.json으로 docs/index.html 재렌더
4. verify-task.js → 커밋 → push → complete-task

## 완료 기준

- 안 읽음 버튼에 체크박스가 보이고 켜면 체크가 채워진다
- 토글해도 화면이 좌우로 밀리지 않는다 (scrollbar-gutter:stable 적용)
- pytest·린트 통과
- **완료일**: 2026-08-05T18:26:44.013Z
