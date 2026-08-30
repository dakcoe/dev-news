from collections import defaultdict
from datetime import datetime, timezone


def _normalize_title(title: str) -> str:
    return " ".join(title.lower().split())


def _time_decay(published_at) -> float:
    if not published_at:
        return 1.0
    try:
        if isinstance(published_at, str):
            from datetime import datetime as _dt
            ts = _dt.fromisoformat(published_at.replace("Z", "+00:00")).timestamp()
        else:
            ts = float(published_at)
        age_hours = (datetime.now(timezone.utc).timestamp() - ts) / 3600
    except Exception:
        return 1.0
    if age_hours <= 8:
        return 2.0
    elif age_hours <= 24:
        return 1.0
    elif age_hours <= 168:
        return 0.5
    else:
        return 0.05


def score_and_categorize(articles: list[dict], top_n: int = 12) -> list[dict]:
    title_sources: dict[str, set] = defaultdict(set)
    for a in articles:
        key = _normalize_title(a["title"])[:60]
        title_sources[key].add(a["source"])

    scored = []
    for a in articles:
        key = _normalize_title(a["title"])[:60]
        # dedup.merge_duplicates가 이미 세어 놓았으면 그 값을 쓴다. 여기 제목
        # 완전일치는 한국어 제목과 영어 제목을 절대 못 묶는다 — 병합 결과가 더 정확하다.
        cross_source_count = a.get("cross_source_count") or len(title_sources[key])
        upvotes = a.get("upvotes", 0) or 0
        comments = a.get("comments", 0) or 0
        decay = _time_decay(a.get("published_at"))
        score = ((upvotes * 1.0) + (comments * 1.5) + (cross_source_count * 300)) * decay

        if cross_source_count >= 2:
            category = "multi_source"
        elif comments > 0 and upvotes > 0 and (comments / max(upvotes, 1)) > 0.4:
            category = "hot_debate"
        else:
            category = "trending"

        scored.append({**a, "score": score, "category": category, "cross_source_count": cross_source_count})

    seen_urls: set[str] = set()
    unique = []
    for a in sorted(scored, key=lambda x: x["score"], reverse=True):
        if a["url"] not in seen_urls:
            seen_urls.add(a["url"])
            unique.append(a)

    return unique[:top_n]
