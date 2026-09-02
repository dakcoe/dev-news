# EXEC_PLAN: remove-tag-cap

- **타입**: fix
- **프로젝트**: project/dev-news
- **상태**: COMPLETED
- **생성일**: 2026-09-02T12:18:20.094Z

## 목표

태그 개수 상한(MAX_TAGS=4)을 없애, 매칭된 태그가 전부 기사에 붙도록 한다.
(8/31 `zhaoxuya520 / reverse-skill` — security가 매칭됐는데도 AI 그룹 4개에 밀려 사라짐)

## 접근법

- `tags.py`: `got[:MAX_TAGS]` 절단 제거. MAX_TAGS 상수와 관련 주석·docstring 정리.
- `template.html` `rowHTML`: `(d.tags||[]).slice(0,4)` 절단 제거.
- 태거는 결정적이므로 `scripts/retag.py`로 전체 코퍼스 소급 재태깅.

## 단계별 계획

1. 재현 테스트 작성 — reverse-skill 기사에 security·open-source가 포함되는지 (RED)
2. tags.py 절단 제거, `test_max_tags_tightened` 삭제 (GREEN)
3. template.html slice(0,4) 제거
4. verify-task → retag.py 실행 → 커밋

## 완료 기준

- pytest 전체 통과
- reverse-skill 기사 태그에 security 포함 (data/articles/2026-08.json 재태깅 결과)
- docs/index.html 재렌더
- **완료일**: 2026-09-02T12:19:31.422Z
