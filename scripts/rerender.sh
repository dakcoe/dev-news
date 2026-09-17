#!/usr/bin/env bash
# 화면(템플릿·설정)만 고쳤을 때 페이지를 다시 만들어 올린다. 수집도 요약도 없다.
#
# 반드시 pull 부터 한다. 수집은 다른 클론(스케줄러 쪽)이 하므로 이 작업 폴더는
# pull 하기 전엔 최신 기사를 모른다 — 옛 데이터로 docs/index.html 을 만들어
# 푸시하면 원격의 새 페이지와 충돌한다 (2026-09-17 실제로 그랬다).
#
#   scripts/rerender.sh            # pull → 렌더 → 커밋 → 푸시
#   scripts/rerender.sh --no-push  # 로컬에서 보기만 (커밋 안 함)
set -euo pipefail
cd "$(dirname "$0")/.."
PY="venv/bin/python"; [ -x "$PY" ] || PY=python3

git pull --rebase -q origin main
"$PY" - <<'PY'
import sys
from datetime import datetime
sys.path.insert(0, '.')
from build import KST, load_config
from news.core import archive
from news.render import render, write_seo_files
cfg = load_config(); all_a = archive.load_all()
# 수집 시각은 마지막 회차 그대로 — 지금 시각을 찍으면 없는 회차가 생긴다
now = datetime.fromisoformat(max(a["batch"] for a in all_a if a.get("batch")))
if now.tzinfo is None: now = now.replace(tzinfo=KST)
render(archive.recent(all_a, cfg.get("scraper", {}).get("keep_days", 30)), "docs/index.html",
       collected=now, enabled=cfg.get("sources", {}), ads=cfg.get("ads"), about=cfg.get("about"))
write_seo_files("docs", now)
PY
[ "${1:-}" = "--no-push" ] && { echo "렌더만 했다 — docs/ 를 보고 git checkout -- docs 로 되돌려도 된다"; exit 0; }
git add -A docs
git diff --staged --quiet && { echo "페이지 변경 없음"; exit 0; }
git commit -q -m "chore: 화면 변경분을 페이지에 반영 (수집 없음)"
git push -q origin main && echo "푸시 $(git rev-parse --short HEAD)"
