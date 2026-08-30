"""피드별 상한 (per-feed-limits).

재현하는 결함: per_source는 source(rss) 단위라 rss 5칸을 어느 피드가 가져가는지
통제하지 못했다. 글을 많이 쓰는 매체가 후보 수로 이겨 최근 10배치 rss 43건 중
The Decoder가 30건(70%)을 차지했다.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from news.core.select import pick  # noqa: E402


def _feed_arts(feed, n, score=900):
    return [{"url": f"https://{feed}.com/{i}", "title": f"{feed}-{i}",
             "source": "rss", "feed": feed, "score": score - i} for i in range(n)]


def _counts(picked, key):
    out = {}
    for a in picked:
        k = a.get(key)
        out[k] = out.get(k, 0) + 1
    return out


def test_one_feed_cannot_dominate():
    arts = _feed_arts("The Decoder", 20, 900) + _feed_arts("Simon Willison", 5, 500)
    got = pick(arts, top_n=10, per_source=10, quota={}, per_feed_page=2)
    counts = _counts(got, "feed")
    assert counts.get("The Decoder") == 2
    assert counts.get("Simon Willison") == 2


def test_items_without_feed_are_unaffected():
    arts = [{"url": f"https://hn.com/{i}", "title": f"hn-{i}",
             "source": "hackernews", "score": 900 - i} for i in range(10)]
    got = pick(arts, top_n=8, per_source=8, quota={}, per_feed_page=2)
    assert len(got) == 8


def test_source_cap_still_applies():
    arts = (_feed_arts("A", 5, 900) + _feed_arts("B", 5, 800) + _feed_arts("C", 5, 700))
    got = pick(arts, top_n=20, per_source=4, quota={}, per_feed_page=2)
    assert len(got) == 4, "source 상한 4가 우선 적용돼야 한다"


def test_without_setting_behaves_as_before():
    arts = _feed_arts("The Decoder", 20, 900)
    assert len(pick(arts, top_n=10, per_source=10, quota={})) == 10


def test_quota_sources_are_not_capped_by_feed():
    """예약석은 출처 단위 보장이다 — github에는 feed 키가 없다."""
    gh = [{"url": f"https://github.com/{i}", "title": f"gh-{i}",
           "source": "github", "score": 100 - i} for i in range(10)]
    got = pick(gh + _feed_arts("The Decoder", 10, 900), top_n=20,
               per_source=5, quota={"github": 5}, per_feed_page=2)
    assert _counts(got, "source").get("github") == 5
