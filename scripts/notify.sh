#!/usr/bin/env bash
# 알림을 로그에만 남긴다 (scripts/publish.sh 가 logs/publish.log 로 보낸다).
#
#   scripts/notify.sh "<제목>" "<본문>"
#
# GitHub 이슈로는 보내지 않는다. 회차마다 같은 이슈에 댓글이 쌓여 알림만 늘었다.
# 이상이 있었는지는 logs/publish.log 에서 "[알림]" 으로 찾는다.
set -euo pipefail

echo "[알림] $1 — $2"
