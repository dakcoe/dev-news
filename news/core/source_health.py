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

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_PATH = os.path.join(ROOT, "data", "source_health.json")
KEEP = 30           # 보관할 회차 수 (하루 3회 → 열흘)
DEFAULT_STREAK = 3  # 연속 0건 판정 회차 수 (하루)


def load(path: str = DEFAULT_PATH) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def record(counts: dict[str, int], when: str,
           path: str = DEFAULT_PATH, keep: int = KEEP) -> list[dict]:
    """회차 결과를 뒤에 붙이고 최근 keep개만 남긴다. 갱신된 이력을 돌려준다."""
    history = load(path)
    history.append({"at": when, "counts": dict(counts)})
    history = history[-keep:]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=1)
    return history


def silent(history: list[dict], streak: int = DEFAULT_STREAK) -> list[str]:
    """마지막 streak 회차에 전부 등장하면서 전부 0건인 출처 이름 (정렬)."""
    if streak <= 0 or len(history) < streak:
        return []
    recent = [h.get("counts", {}) for h in history[-streak:]]
    names = set(recent[0])
    for c in recent[1:]:
        names &= set(c)
    return sorted(n for n in names if all(c.get(n, 0) == 0 for c in recent))
