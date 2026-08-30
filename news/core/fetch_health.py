"""본문 수집 결과 기록 (record-fetch-failures).

실패가 print로만 나가고 사라지면 나중에 원인을 알 수 없다. 이번 프로젝트에서
실제로 겪었다 — 실패를 분류하려고 최근 250건 URL에 요청을 다시 날리는 재현
스크립트를 따로 짜야 했고, 그 결과가 이후 작업 세 개의 근거가 됐다.

추가 요청은 하지 않는다. enrich가 이미 받아 온 응답에서 알 수 있는 것만 적는다.

기록은 부가 기능이다 — 파일이 깨졌거나 쓰기에 실패해도 회차를 죽이지 않는다
(api_health와 같은 원칙).
"""
from __future__ import annotations

import json
import os
from datetime import datetime

from news.core.common import KST, ROOT

DEFAULT_PATH = os.path.join(ROOT, "data", "fetch_health.json")

# 회차 기록 보관 수. 무한 누적하면 커밋마다 파일이 커진다.
MAX_RUNS = 30

# 봇 차단으로 보는 응답 코드. 게재 판단에는 ok지만 진단할 때는 구분돼야 한다.
_BLOCKED_CODES = {401, 403, 429}


def reason_of(status: str | None, code: int | None,
              content: str | None, accepted: bool = True) -> str:
    """한 건의 수집 결과를 진단용 사유로 옮긴다.

    classify()가 주는 게재 판단(ok/dead/unknown)보다 잘게 나눈다 — 403과 200은
    게재에는 똑같이 ok지만 원인을 볼 때는 전혀 다르다.
    """
    if status is None:
        return "github"          # raw README 경로 — 판정 대상이 아니다
    if status == "dead":
        return "dead"
    if status == "unknown":
        return "unavailable"
    if code in _BLOCKED_CODES:
        return "blocked"
    if not content:
        return "empty"           # 200인데 추출 실패 (SPA·페이월)
    if not accepted:
        return "short"           # 추출은 됐지만 채택 기준 미달
    return "ok"


def load(path: str = DEFAULT_PATH) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("runs"), list):
            return data
    except Exception:
        pass
    return {"runs": []}


def record(rows: list[dict], path: str = DEFAULT_PATH) -> None:
    """한 회차 결과를 누적한다. rows는 {url, source, reason} 목록."""
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["reason"]] = counts.get(r["reason"], 0) + 1

    run = {
        "at": datetime.now(KST).isoformat(timespec="seconds"),
        "total": len(rows),
        "counts": counts,
        "failures": [{"url": r["url"], "source": r.get("source", ""),
                      "reason": r["reason"]}
                     for r in rows if r["reason"] not in ("ok", "github")],
    }

    data = load(path)
    data["runs"] = (data["runs"] + [run])[-MAX_RUNS:]

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print(f"[fetch] 기록 실패(무시): {e}")
        return

    if run["failures"]:
        summary = " · ".join(f"{k} {v}" for k, v in sorted(counts.items())
                             if k not in ("ok", "github"))
        print(f"[fetch] 실패 사유 {summary} → {path}")
