"""출처별 수집 건수 기록과 침묵 감지 (add-source-silence-alert).

github·trendshift·anthropic은 HTML을 파싱한다. 상대 사이트가 화면을 바꾸면
에러가 아니라 0건이 나온다. 다른 출처가 top_n을 채우면 게시 건수 기반
열화 알림(alert.min_published)에는 안 걸리므로, 출처 단위로 따로 본다.

한 회차 0건은 정상일 수 있다(타임아웃·일시 장애). 연속 streak 회차가 전부
0건일 때만 침묵으로 판정한다. 꺼진 출처는 counts에 아예 없으므로 대상이 아니다.
"""
from __future__ import annotations

import json
import os
from datetime import datetime

from news.core.common import ROOT, load_json
DEFAULT_PATH = os.path.join(ROOT, "data", "source_health.json")
KEEP = 30           # 보관할 회차 수 (하루 3회 → 열흘)
DEFAULT_STREAK = 3  # 연속 0건 판정 회차 수 (하루)


def load(path: str = DEFAULT_PATH) -> list[dict]:
    """record() 가 이 값 뒤에 이번 회차를 붙여 같은 경로에 다시 쓴다. 빈
    목록으로 돌려주면 30회차 이력이 1회로 줄고, silent() 의 이력 부족 조건
    때문에 그 뒤 최소 streak 회차 동안 침묵 판정 자체가 불가능해진다."""
    return load_json(path, [])


def record(counts: dict[str, int], when: str,
           path: str = DEFAULT_PATH, keep: int = KEEP,
           skip_days: dict[str, list[int]] | None = None) -> list[dict]:
    """회차 결과를 뒤에 붙이고 최근 keep개만 남긴다. 갱신된 이력을 돌려준다.

    skip_days 는 출처가 발행을 쉬는 요일(0=월 … 6=일)이다 (feed-skip-days). 피드가 <skipDays>로
    직접 알려준 값만 들어온다.
    """
    history = load(path)
    entry = {"at": when, "counts": dict(counts)}
    if skip_days:
        entry["skip"] = {k: list(v) for k, v in skip_days.items() if v}
    history.append(entry)
    history = history[-keep:]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=1)
    return history


def _weekday(at: str) -> int | None:
    try:
        return datetime.fromisoformat(at).weekday()
    except (TypeError, ValueError):
        return None


def silent(history: list[dict], streak: int = DEFAULT_STREAK) -> list[str]:
    """마지막 streak 회차에 전부 등장하면서 전부 0건인 출처 이름 (정렬).

    출처가 <skipDays>로 쉰다고 밝힌 요일의 회차는 그 출처에 한해 세지 않는다.
    arXiv 는 주말에 <item> 이 없는 껍데기를 주므로, 그걸 모르면 매주 토·일에
    죽은 출처로 잡힌다. 쉬는 날을 빼고 나서 셀 회차가 없으면 판정하지 않는다.
    """
    if streak <= 0 or len(history) < streak:
        return []
    names = set(history[-streak:][0].get("counts", {}))
    for h in history[-streak:][1:]:
        names &= set(h.get("counts", {}))

    out = []
    for n in names:
        # 휴재 요일 회차는 빼고, 남은 것 중 최근 streak개로 판정한다. 그만큼
        # 모이지 않았으면 아직 판정하지 않는다 — 한 회차 0건은 정상일 수 있다는
        # 원래 기준을 휴재 요일을 빼고도 지키려면 창을 뒤로 넓혀야 한다.
        judged = [h for h in history
                  if n in h.get("counts", {})
                  and _weekday(h.get("at", "")) not in (h.get("skip", {}).get(n) or [])]
        judged = judged[-streak:]
        if len(judged) >= streak and all(h["counts"].get(n, 0) == 0 for h in judged):
            out.append(n)
    return sorted(out)
