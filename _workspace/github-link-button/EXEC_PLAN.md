# EXEC_PLAN: github-link-button

- **상태:** IN_PROGRESS
- **유형:** feat
- **생성:** 2026-09-02

## 목표
뉴스 페이지 왼쪽 레일(.rail) 하단에 GitHub 저장소(https://github.com/dakcoe/dev-news)로
연결되는 링크 버튼을 추가한다.

## 접근법
- `news/template.html`의 `<nav class="rail">` 마지막에 `<a class="rb gh">` 추가
  (버튼이 아니라 외부 링크이므로 `<a>` + `target="_blank"`).
- 데스크톱: `.rb.gh{margin-top:auto}`로 레일 맨 아래에 고정.
- 모바일(하단 내비 전환 시): `margin-top:0`으로 되돌려 다른 버튼과 나란히 배치.
- 뷰 전환 JS는 `data-v` 유무로 동작하므로 링크에는 `data-v`를 주지 않는다.

## 단계별 계획
1. RED — `tests/test_github_link.py`: 템플릿에 저장소 링크 존재 확인 테스트
2. GREEN — 템플릿에 마크업·CSS 추가
3. 브라우저에서 데스크톱/모바일 폭 렌더링 확인
4. verify-task.js → 커밋

## 완료 기준
- 데스크톱: 레일 맨 아래 GitHub 아이콘, 클릭 시 새 탭으로 저장소 열림
- 모바일 폭: 하단 내비에 아이콘 표시, 겹침 없음
- 뷰 전환 로직에 영향 없음 (링크가 .on 토글 대상이 되지 않음)
- pytest + ruff 통과
