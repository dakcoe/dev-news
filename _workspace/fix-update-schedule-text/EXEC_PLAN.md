# EXEC_PLAN: fix-update-schedule-text

- **타입**: fix
- **프로젝트**: project/dev-news
- **상태**: IN_PROGRESS
- **생성일**: 2026-08-11T14:44:08.529Z

## 목표

페이지 안내 문구가 실제 수집 스케줄과 다르다. GitHub Actions는 KST 00시/08시/16시
(cron `0 7,15,23 * * *` UTC) 하루 3회 실행되는데, 화면에는 "매일 오전 9시"로 표시된다.
문구를 실제 스케줄에 맞게 고친다.

## 접근법

페이지는 `news/template.html` 단일 파일(CSS+JS 인라인)에서 렌더되고
`docs/index.html`은 그 산출물이므로, 템플릿만 고치고 재렌더한다.
동일 문구가 README.md / SPEC.md 문서에도 남아 있어 함께 정정한다.

## 단계별 계획

1. `news/template.html` 두 곳(소스 뷰 서브텍스트, 뉴스 뷰 서브텍스트) 문구 수정
2. 회귀 테스트 추가: 템플릿에 "9시" 문구가 없고 "00시·08시·16시" 문구가 있는지 검사
3. `python scripts/retag.py` 등 재렌더로 `docs/index.html` 갱신
4. README.md · SPEC.md 스케줄 서술 정정
5. `node scripts/verify-task.js project/dev-news` 검증 → 커밋 → complete-task

## 완료 기준

- `news/template.html`, `docs/index.html`에 "오전 9시" 문구가 남아 있지 않음
- 새 회귀 테스트를 포함해 pytest 전체 통과
- 페이지 렌더 결과에 "매일 00시·08시·16시" 안내가 표시됨
