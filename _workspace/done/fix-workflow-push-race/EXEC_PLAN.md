# EXEC_PLAN: fix-workflow-push-race

- **타입**: fix
- **프로젝트**: project/dev-news
- **상태**: COMPLETED
- **생성일**: 2026-08-06T00:20:25.505Z

## 목표

워크플로우가 오래된 체크아웃(Re-run) 또는 동시 push 때문에 `git push`에서
"fetch first"로 거부되어 수집 결과를 통째로 버리는 문제를 없앤다.

## 원인 진단 (Actions API로 확인)

오늘 아침 실행은 어제 run #1의 **Re-run**이어서 `head: ebee029`(어제 스냅샷)를
체크아웃했다. 어젯밤 디자인 커밋 4개가 원격에 있었으므로 push가 거부됐고,
러너가 폐기되며 수집·요약 결과(20건)도 사라졌다. seen.json도 push되지 않았으므로
재실행하면 같은 기사를 다시 수집할 수 있어 영구 손실은 없다.

## 접근법

`.github/workflows/daily.yml`의 커밋 단계에서 push 직전에
`git pull --rebase -X theirs origin main`을 실행한다.

- rebase: 원격의 새 커밋 위에 봇 커밋을 다시 얹는다 → fast-forward push 가능
- `-X theirs`: docs/data 생성 파일이 충돌하면 방금 빌드한 쪽(봇 커밋)을 남긴다
  (rebase 중에는 theirs = 재적용되는 로컬 커밋)

## 단계별 계획

1. daily.yml 커밋 단계에 pull --rebase 추가
2. tests/test_workflow.py — 워크플로우 yml에 rebase 방어 코드가 있는지 회귀 테스트
3. verify-task.js → 커밋 → push → complete-task
4. 사용자에게 "Run workflow"(새 실행)로 오늘 뉴스 재수집 안내

## 완료 기준

- daily.yml에 pull --rebase -X theirs가 push 앞에 존재
- pytest·린트 통과
- 다음 워크플로우 실행이 push까지 성공 (봇 커밋 생성 확인)
- **완료일**: 2026-08-06T00:22:41.277Z
