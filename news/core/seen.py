"""이미 소개한 기사를 기억한다.

봇은 SQLite를 쓰지만 GitHub Actions는 실행마다 환경이 초기화되므로
JSON 파일에 저장하고 워크플로가 그 파일을 리포에 커밋한다.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from news.core.common import ROOT
from news.core.dedup import normalize_url

DEFAULT_PATH = os.path.join(ROOT, "data", "seen.json")


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
    """비교용 키 집합. 같은 기사인지는 중복제거와 같은 규칙으로 가린다.

    예전에는 주소 문자열을 그대로 비교해서, 끝 슬래시 하나나 # 뒤 조각 차이만
    있어도 다른 기사로 봤다. 아카이브에 같은 글이 두 번 실린 사례가 있다.
    옛 파일에는 다듬기 전 주소가 키로 들어 있으므로 읽을 때 함께 맞춘다.
    """
    return {normalize_url(k) or k for k in _load(path)}


def filter_unseen(articles: list[dict], path: str = DEFAULT_PATH) -> list[dict]:
    seen = load_seen(path)
    # 기억 상태를 항상 찍는다. 0건이면 seen.json이 비었거나 덮어써진 것이다.
    print(f"[seen] 기억 중인 URL {len(seen)}건 ({path})")
    fresh = [a for a in articles if (normalize_url(a["url"]) or a["url"]) not in seen]
    if len(fresh) != len(articles):
        print(f"[seen] 이미 소개한 {len(articles) - len(fresh)}건 제외")
    return fresh


def mark_seen(articles: list[dict], path: str = DEFAULT_PATH) -> None:
    # 영구 유지 (SPEC 2.3) — 만료를 두면 30일 뒤 다시 트렌딩에 오른 기사가 중복 등장한다.
    # URL 집합이라 무한 누적해도 용량 문제가 없다.
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
