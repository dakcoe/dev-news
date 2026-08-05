"""수집한 기사를 누적 보관한다.

매 실행마다 새 기사를 앞에 붙이고, 페이지는 전체를 수집 회차별로 묶어 보여준다.
너무 무거워지지 않게 보관 기간과 최대 건수로 자른다.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "articles.json",
)


def load(path: str = DEFAULT_PATH) -> list[dict]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"[archive] 읽기 실패({e}) — 빈 목록으로 시작합니다")
        return []


def save(articles: list[dict], path: str = DEFAULT_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=1)


def append(new_items: list[dict], batch: datetime,
           keep_days: int = 30, max_items: int = 300,
           path: str = DEFAULT_PATH) -> list[dict]:
    """새 기사에 수집 회차를 찍어 기존 목록 앞에 붙이고, 오래된 건 잘라낸다."""
    old = load(path)
    known = {a.get("url") for a in old}

    stamped = []
    for a in new_items:
        if a.get("url") in known:
            continue
        stamped.append({**a, "batch": batch.isoformat(),
                        "batch_label": f"{batch.month}월 {batch.day}일 {batch:%H:%M}"})

    merged = stamped + old

    cutoff = (datetime.now(timezone.utc) - timedelta(days=keep_days)).timestamp()
    kept = []
    for a in merged:
        try:
            ts = datetime.fromisoformat(a["batch"]).timestamp()
        except Exception:
            ts = cutoff + 1          # 회차 정보가 없으면 일단 남긴다
        if ts >= cutoff:
            kept.append(a)

    if len(kept) > max_items:
        kept = kept[:max_items]

    save(kept, path)
    print(f"[archive] 신규 {len(stamped)}건 추가 · 누적 {len(kept)}건 (최근 {keep_days}일)")
    return kept
