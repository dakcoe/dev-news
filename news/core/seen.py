"""이미 소개한 기사를 기억한다.

봇은 SQLite를 쓰지만 GitHub Actions는 실행마다 환경이 초기화되므로
JSON 파일에 저장하고 워크플로가 그 파일을 리포에 커밋한다.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "data", "seen.json")

KEEP_DAYS = 30


def _load(path: str) -> dict[str, str]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_seen(path: str = DEFAULT_PATH) -> set[str]:
    return set(_load(path).keys())


def filter_unseen(articles: list[dict], path: str = DEFAULT_PATH) -> list[dict]:
    seen = load_seen(path)
    # 기억 상태를 항상 찍는다. 0건이면 seen.json이 비었거나 덮어써진 것이다.
    print(f"[seen] 기억 중인 URL {len(seen)}건 ({path})")
    fresh = [a for a in articles if a["url"] not in seen]
    if len(fresh) != len(articles):
        print(f"[seen] 이미 소개한 {len(articles) - len(fresh)}건 제외")
    return fresh


def mark_seen(articles: list[dict], path: str = DEFAULT_PATH) -> None:
    data = _load(path)
    now = datetime.now(timezone.utc)
    for a in articles:
        data[a["url"]] = now.isoformat()

    cutoff = now - timedelta(days=KEEP_DAYS)
    pruned = {}
    for url, ts in data.items():
        try:
            if datetime.fromisoformat(ts) >= cutoff:
                pruned[url] = ts
        except Exception:
            pruned[url] = ts

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(pruned, f, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"[seen] {len(articles)}건 기록 · 보관 {len(pruned)}건")
