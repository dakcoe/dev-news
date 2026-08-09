# EXEC_PLAN: tagbtn-below-sources

- **타입**: fix
- **프로젝트**: project/dev-news
- **상태**: IN_PROGRESS
- **생성일**: 2026-08-09T06:02:12.066Z

## 목표

"태그" 버튼을 소스 칩 줄(Hacker News·GitHub 등) 맨 앞에서 그 아래 별도 줄로 이동 (사용자 요청).

## 접근법

- chipsHTML에서 tagbtn 제거, render()에서 칩 줄 다음에 .tagrow(전용 줄)로 렌더.
- 노출 제어를 #tagbtn에서 .tagrow로 이전: 기본 숨김, 접힘 시 .show, ≤900px 상시.
  숨김 상태에서 빈 줄 공간이 생기지 않도록 wrapper 자체를 display:none.
- 버튼 스타일(.tagcp 보라 강조)은 그대로.

## 단계별 계획

1. 테스트 갱신: tagbtn이 barHTML·chipsHTML 밖 .tagrow에 있는지 검증
2. template.html 수정 → retag 재렌더 → 브라우저 확인
3. verify → 커밋 → 완료 처리

## 완료 기준

- [ ] pytest 전체·ruff 통과, 접힘/모바일에서 소스 칩 아래 줄에 태그 버튼 노출
