"""무엇을 실을지 정하는 선별 (move-pipeline-to-core).

build.py에 있던 것을 옮겼다. 필터(filters.py)가 걸러낸 뒤 남은 후보에서
점수·예약석·출처 상한을 적용해 최종 목록을 만든다.
"""
from __future__ import annotations

from collections import defaultdict


def adjust_scores(articles: list[dict], cfg: dict) -> list[dict]:
    """출처별 기본점수·가중치 보정 (deprecated — 동점 처리용으로만 남김, SPEC 1.5).

    UI에서 점수 표시는 제거됐다. 이 보정은 top_n 선별의 정렬 기준으로만 쓰인다.
    """
    base = cfg.get("source_base", {})
    weight = cfg.get("source_weight", {})
    for a in articles:
        src = a.get("source", "")
        a["score"] = (a.get("score", 0) + base.get(src, 0)) * weight.get(src, 1.0)
    articles.sort(key=lambda x: x.get("score", 0), reverse=True)
    return articles


def pick(articles: list[dict], top_n: int, per_source: int,
         quota: dict[str, int] | None = None,
         per_feed_page: int | None = None) -> list[dict]:
    """점수순 목록에서 최종 선별.

    source_quota는 우선권이 아니라 **예약석**이다.

    1단계 — quota에 적힌 출처가 그 개수를 가져간다. 점수와 무관하게 자리를
            보장받고, 동시에 그 개수를 넘지도 않는다(상한이기도 하다).
    2단계 — 나머지 출처가 `top_n - 예약분 합계`만큼을 점수순으로 채운다.

    per_feed_page는 2단계에 피드 단위 상한을 더한다. per_source는 source(rss)
    단위라 rss 5칸을 어느 피드가 가져가는지 통제하지 못했다 — 글을 많이 쓰는
    매체가 후보 수로 이겨 최근 10배치 rss 43건 중 The Decoder가 30건이었다.
    `feed` 키가 있는 아이템에만 걸린다(rss·anthropic만 이 키를 채운다).

    2단계 목표가 top_n이 아니라는 것이 핵심이다. top_n까지 채우면 예약 출처가
    부족할 때 그 자리를 일반 기사가 가져간다 — github가 4건이면 일반이 16건
    들어와 20건이 됐다. 예약석은 비워 두고 19건으로 끝내는 것이 맞다.
    """
    quota = quota or {}
    counts: dict[str, int] = defaultdict(int)
    picked: list[dict] = []
    taken: set[int] = set()

    for src, n in quota.items():
        for i, a in enumerate(articles):
            if counts[src] >= n or len(picked) >= top_n:
                break
            if i in taken or a["source"] != src:
                continue
            taken.add(i)
            counts[src] += 1
            picked.append(a)
        if counts[src] < n:
            print(f"[선별] {src} 보장 {n}건 중 {counts[src]}건만 확보 (후보 부족)")

    reserved = min(sum(quota.values()), top_n)
    general_limit = max(top_n - reserved, 0)
    general_taken = 0
    feed_counts: dict[str, int] = defaultdict(int)

    for i, a in enumerate(articles):
        if general_taken >= general_limit:
            break
        if i in taken or a["source"] in quota:   # 예약 출처는 1단계에서만 뽑는다
            continue
        cap = per_source
        if counts[a["source"]] >= cap:
            continue
        feed = a.get("feed")
        if per_feed_page and feed and feed_counts[feed] >= per_feed_page:
            continue
        taken.add(i)
        counts[a["source"]] += 1
        if a.get("feed"):
            feed_counts[a["feed"]] += 1
        general_taken += 1
        picked.append(a)

    if general_taken < general_limit:
        print(f"[선별] 일반 {general_limit}칸 중 {general_taken}건만 확보 (후보 부족)")

    picked.sort(key=lambda x: x.get("score", 0), reverse=True)
    print("[선별] " + " · ".join(f"{k} {v}" for k, v in sorted(counts.items()) if v))
    return picked
