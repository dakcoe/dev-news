#!/usr/bin/env bash
# 알림을 GitHub 이슈로 남긴다 (add-failure-alert).
#
#   scripts/notify.sh "<제목>" "<본문>"
#
# 열려 있는 같은 제목의 이슈가 있으면 댓글로 붙이고, 없으면 새로 연다.
# 중복 방지가 핵심이다 — 매번 새로 만들면 연속 실패에 이슈가 쌓여서 그것도 묻힌다.
# 이슈 하나가 "연속 몇 번 깨졌는지" 타임라인이 되고, 고쳐서 닫으면 다음에 새로 열린다.
#
# GH_TOKEN 환경변수와 워크플로의 `permissions: issues: write`가 필요하다.
set -euo pipefail

TITLE="$1"
BODY="$2"

# jq의 env.TITLE로 넘긴다 — 제목에 따옴표가 섞여도 안전하다.
NUM=$(TITLE="$TITLE" gh issue list --state open --limit 50 --json number,title \
      --jq '[.[] | select(.title == env.TITLE)][0].number // empty')

if [ -n "$NUM" ]; then
  gh issue comment "$NUM" --body "$BODY"
  echo "[notify] 기존 이슈 #$NUM에 기록"
else
  gh issue create --title "$TITLE" --body "$BODY"
  echo "[notify] 새 이슈 생성: $TITLE"
fi
