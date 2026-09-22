"""이미 소개한 기사를 기억한다.

봇은 SQLite를 쓰지만 GitHub Actions는 실행마다 환경이 초기화되므로
JSON 파일에 저장하고 워크플로가 그 파일을 리포에 커밋한다.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from news.core.common import KST, ROOT, load_json
from news.core.dedup import normalize_url

DEFAULT_PATH = os.path.join(ROOT, "data", "seen.json")


def _load(path: str) -> dict[str, str]:
    """mark_seen() 이 이 값에 오늘 것을 얹어 같은 경로에 다시 쓴다. 빈 dict 로
    돌려주면 영구 보관(SPEC 2.3) 기록이 이번 회차 20여 건으로 줄어 커밋된다."""
    return load_json(path, {})


def load_seen(path: str = DEFAULT_PATH) -> set[str]:
    """비교용 키 집합. 같은 기사인지는 중복제거와 같은 규칙으로 가린다.

    예전에는 주소 문자열을 그대로 비교해서, 끝 슬래시 하나나 # 뒤 조각 차이만
    있어도 다른 기사로 봤다. 아카이브에 같은 글이 두 번 실린 사례가 있다.
    옛 파일에는 다듬기 전 주소가 키로 들어 있으므로 읽을 때 함께 맞춘다.
    """
    return {normalize_url(k) or k for k in _load(path)}


def _seen_at(value: str):
    """기록 시각. 옛 파일에는 다른 형식이 섞여 있을 수 있다 — 못 읽으면 None."""
    try:
        dt = datetime.fromisoformat(str(value))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def filter_unseen(articles: list[dict], path: str = DEFAULT_PATH,
                  resurface_days: dict[str, int] | None = None) -> list[dict]:
    """이미 소개한 기사를 뺀다.

    resurface_days 에 든 출처는 예외다 — 기록된 지 그 날짜가 지났으면 다시
    후보가 되고, 기사에 resurfaced(지난 게시일)가 붙는다. 깃허브 저장소가 몇 달
    뒤 다시 트렌딩에 오르는 경우를 위한 것이다. 기록 시각을 못 읽는 항목은
    안전하게 '본 것'으로 친다.
    """
    raw = _load(path)
    seen = {normalize_url(k) or k: v for k, v in raw.items()}
    print(f"[seen] 기억 중인 URL {len(seen)}건 ({path})")
    rule = resurface_days or {}
    now = datetime.now(timezone.utc)
    fresh, again = [], 0
    for a in articles:
        key = normalize_url(a["url"]) or a["url"]
        if key not in seen:
            fresh.append(a)
            continue
        days = rule.get(a.get("source") or "")
        at = _seen_at(seen[key]) if days else None
        if at is not None and (now - at).days >= days:
            # 게시일은 KST 로 적는다. 아카이브의 batch 가 KST 라 archive.append 가
            # 둘을 날짜 문자열로 비교한다 — UTC 로 적으면 00·08시 회차 기사는
            # 하루 앞선 날짜가 돼 요약까지 받고도 저장되지 않는다.
            fresh.append({**a, "resurfaced": at.astimezone(KST).date().isoformat()})
            again += 1
    if len(fresh) != len(articles):
        print(f"[seen] 이미 소개한 {len(articles) - len(fresh)}건 제외")
    if again:
        print(f"[seen] 기간이 지나 다시 후보가 된 {again}건")
    return fresh


def mark_seen(articles: list[dict], path: str = DEFAULT_PATH) -> None:
    # 영구 유지 (SPEC 2.3). 다시 실을 수 있는 출처(config seen.resurface_days)는
    # 읽을 때 기록 시각으로 가리므로 여기서는 늘 지금 시각으로 덮어쓴다 —
    # 다시 실리면 그때부터 다시 기간을 센다.
    # 키를 정규화해 다시 쓴다. 옛 파일의 원문 주소 키도 이때 한 번에 맞춰진다.
    old = _load(path)
    data: dict[str, str] = {}
    for k, v in old.items():
        data.setdefault(normalize_url(k) or k, v)

    now = datetime.now(timezone.utc)
    for a in articles:
        # 중복제거가 한 건으로 합친 주소를 전부 기억한다. 대표 주소 하나만 넣으면
        # 다음 회차에 다른 쪽 주소가 처음 보는 글로 판정돼 같은 기사가 다시 실린다.
        for url in (a.get("merged_urls") or [a["url"]]):
            data[normalize_url(url) or url] = now.isoformat()

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"[seen] {len(articles)}건 기록 · 보관 {len(data)}건 (영구)")
