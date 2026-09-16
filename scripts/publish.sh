#!/usr/bin/env bash
# 수집 → 요약 → 페이지 생성 → 커밋 → 푸시. 스케줄러(launchd·cron)가 부른다.
#
# 왜 GitHub Actions 가 아니라 여기서 도나. 깃허브 러너의 IP 를 여러 사이트가 막아
# 본문 추출이 8% 실패했고(서브스택·digiato 등은 집에서 받으면 멀쩡했다), 예약
# 실행이 2~5시간 늦게 시작했다. 자기 기계에서 돌리면 둘 다 없다. 커밋도 자기
# 계정으로 남는다.
#
# 쓰는 법:  scripts/publish.sh            (저장소 어디서 불러도 된다)
#   - .env 에 GROQ_API_KEY 가 있어야 한다 (.env.example 참고)
#   - gh 가 로그인돼 있어야 한다 — GitHub API 한도와 알림 이슈에 쓴다
#   - 로그는 logs/publish.log 에 쌓인다 (gitignore)
#
# 실패·열화·출처 침묵은 워크플로 때와 같이 scripts/notify.sh 로 이슈를 연다.
set -uo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs
LOG="logs/publish.log"
exec >>"$LOG" 2>&1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
export TZ=Asia/Seoul
STAMP="$(date '+%Y-%m-%d %H:%M')"
echo "===== $STAMP 시작"

PY="venv/bin/python"
[ -x "$PY" ] || { echo "venv 가 없다 — python3.12 -m venv venv && venv/bin/pip install -r requirements.txt"; exit 1; }

# GitHub API 한도(시간당 60 → 1,000+)와 알림 이슈에 쓴다. 토큰 값은 로그에 안 남긴다.
export GITHUB_TOKEN GH_TOKEN
GITHUB_TOKEN="$(gh auth token 2>/dev/null || true)"; GH_TOKEN="$GITHUB_TOKEN"

# 원격이 앞서 있으면 먼저 받는다 (다른 기계에서 고친 코드·수동 회차).
git pull --rebase -q origin main || { echo "pull 실패"; }

# build.py 는 GITHUB_OUTPUT 파일에 published/degraded/silent 를 적는다.
OUT="$(mktemp)"; export GITHUB_OUTPUT="$OUT"
if ! "$PY" build.py; then
  echo "build.py 실패"
  bash scripts/notify.sh "🔴 뉴스 수집 실패" \
    "$STAMP 회차가 실패했습니다. 수집 기계의 logs/publish.log 를 보세요."
  exit 1
fi
val() { grep "^$1=" "$OUT" | tail -1 | cut -d= -f2-; }

git add -A docs data
if git diff --staged --quiet; then
  echo "변경 없음 — 커밋 생략"
else
  git commit -q -m "뉴스 갱신 $STAMP"
  # 원격이 그 사이 앞섰으면 데이터를 합친다 (seen·아카이브는 합집합이 맞다)
  git fetch -q origin main
  if ! git merge-base --is-ancestor origin/main HEAD; then
    echo "원격이 앞서 있다 — 데이터를 합친다"
    "$PY" scripts/merge_remote_data.py origin/main
    git add -A docs data
    git diff --staged --quiet || git commit -q -m "원격 회차 데이터 병합"
  fi
  git pull --rebase -X theirs -q origin main
  if ! git push -q origin main; then
    echo "push 실패"
    bash scripts/notify.sh "🔴 뉴스 수집 실패" \
      "$STAMP 회차: 수집은 됐지만 push 가 거부됐습니다. 수집물에 섞인 시크릿(GH013)이면 news/core/redact.py 에 패턴을 추가하세요."
    exit 1
  fi
  echo "push 완료 $(git rev-parse --short HEAD)"
fi

if [ "$(val degraded)" = "true" ]; then
  bash scripts/notify.sh "🟡 게시 건수 급감" \
    "$STAMP 회차는 성공했지만 **$(val published)건**만 게시됐습니다. 임계값은 config.yaml 의 alert.min_published 입니다."
fi
if [ -n "$(val silent)" ]; then
  bash scripts/notify.sh "🟡 출처 침묵" \
    "$STAMP 회차 기준 연속 0건인 출처: **$(val silent)**. news/scrapers/ 의 해당 파일을 확인하세요."
fi
rm -f "$OUT"

# 소개 화면의 후원 링크가 살아 있는지. 외부 서비스라 예고 없이 끝날 수 있다 —
# 만료되면 버튼이 죽은 링크로 남으니 다음 회차에 바로 알아야 한다.
COFFEE="$("$PY" -c 'import yaml;print((yaml.safe_load(open("config.yaml",encoding="utf-8")).get("about") or {}).get("coffee") or "")')"
if [ -n "$COFFEE" ]; then
  code="$(curl -s -o /dev/null -m 15 -w '%{http_code}' -A 'Mozilla/5.0' "$COFFEE" || echo 000)"
  if [ "$code" != "200" ]; then
    echo "후원 링크 응답 $code"
    bash scripts/notify.sh "🟡 후원 링크 응답 이상" \
      "$STAMP 회차: 소개 화면의 후원 링크가 HTTP $code 를 돌려줍니다. 링크가 만료됐으면 config.yaml 의 about.coffee 를 새 주소로 바꾸거나 비우세요."
  fi
fi
echo "===== $(date '+%H:%M') 끝"
