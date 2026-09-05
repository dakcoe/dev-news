# EXEC_PLAN: add-source-silence-alert

- **타입**: feat
- **프로젝트**: project/dev-news
- **상태**: IN_PROGRESS

## 목표

켜져 있는 수집 출처가 연속 N회차(기본 3) 0건이면 Actions가 🟡 이슈로 알린다.
HTML 파싱 출처(github·trendshift·anthropic)는 상대 사이트가 화면을 바꾸면 에러 없이 0건이 되는데,
다른 출처가 20건을 채우면 기존 열화 알림(min_published)에 안 걸린다.

## 접근법

- `news/core/source_health.py`: 회차별 출처 수집 건수를 `data/source_health.json`에 누적(최근 30회차),
  마지막 streak 회차 모두 0건인 출처를 골라낸다. 수집기 예외도 0건으로 센다.
- `build.run_scrapers`가 건수를 out-param으로 채우고, `collect_candidates`가 기록·판정해 침묵 목록을 돌려준다.
- `emit_actions_output`이 `silent=a,b`를 GITHUB_OUTPUT에 추가. 워크플로에 `출처 침묵 알림` 스텝 추가
  (기존 notify.sh 재사용, 제목 고정이라 연속 침묵은 한 이슈에 댓글로 쌓인다).
- 임계는 `config.yaml alert.silent_streak`.

## 단계별 계획

1. tests/test_source_health.py — record 누적·trim, silent 판정(streak 미만 이력·중간 회복·꺼진 출처 제외) (RED)
2. tests/test_alert.py — emit_actions_output의 silent 출력, 워크플로 스텝 게이트
3. 구현: source_health.py, build.py, daily.yml, config.yaml
4. 문서: CONFIG.md 알림 절, GITHUB_ACTIONS.md 알림 표
5. verify-task → 커밋

## 완료 기준

- pytest 전체 통과
- 로컬 `--no-ai` 실행 후 data/source_health.json에 회차 1건이 기록됨
