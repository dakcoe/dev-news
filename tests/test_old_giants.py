"""오래된 대형 저장소는 트렌딩에 걸려도 싣지 않는다 (2026-10-04)."""
from datetime import datetime, timezone

from news.core.filters import drop_old_giants

NOW = datetime(2026, 10, 4, tzinfo=timezone.utc)


def _gh(url):
    return {"url": url, "title": url, "source": "github"}


def test_오래되고_큰_저장소만_뺀다():
    arts = [_gh("old-big"), _gh("old-small"), _gh("new-big"), _gh("unknown"),
            {"url": "hn", "title": "hn", "source": "hackernews"}]
    meta = {"old-big": {"created": "2019-01-01T00:00:00Z", "stars": 44946},
            "old-small": {"created": "2019-01-01T00:00:00Z", "stars": 16435},
            "new-big": {"created": "2026-08-01T00:00:00Z", "stars": 390871},
            "unknown": {}}
    kept = drop_old_giants(arts, meta, now=NOW)
    assert [a["url"] for a in kept] == ["old-small", "new-big", "unknown", "hn"]
