"""예약석 방식 선별 (reserved-github-slots).

기존 `source_quota`는 우선권이었다 — 5칸을 먼저 확보하되, 부족하면 2단계가
`top_n`까지 채우면서 남은 자리를 일반 기사가 가져갔다. 그래서 github가 4건이면
일반이 16건 들어와 20건이 됐다.

원하는 것은 예약석이다: 일반 15 + 트렌딩 5, 트렌딩이 4건이면 19건.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from news.core.select import pick  # noqa: E402

QUOTA = {"github": 5}


def _arts(source, n, start_score=1000):
    return [{"url": f"https://{source}.com/{i}", "title": f"{source}-{i}",
             "source": source, "score": start_score - i} for i in range(n)]


def _counts(picked):
    out = {}
    for a in picked:
        out[a["source"]] = out.get(a["source"], 0) + 1
    return out


def test_reserved_slots_split_15_5():
    arts = _arts("hackernews", 30, 900) + _arts("github", 10, 100)
    got = pick(arts, top_n=20, per_source=15, quota=QUOTA)
    assert len(got) == 20
    assert _counts(got) == {"hackernews": 15, "github": 5}


def test_short_reserved_source_shrinks_total():
    """트렌딩이 4건뿐이면 15+4=19건. 일반이 메우지 않는다."""
    arts = _arts("hackernews", 30, 900) + _arts("github", 4, 100)
    got = pick(arts, top_n=20, per_source=15, quota=QUOTA)
    assert len(got) == 19
    assert _counts(got) == {"hackernews": 15, "github": 4}


def test_no_reserved_candidates_at_all():
    arts = _arts("hackernews", 30, 900)
    got = pick(arts, top_n=20, per_source=15, quota=QUOTA)
    assert len(got) == 15
    assert _counts(got) == {"hackernews": 15}


def test_reserved_source_never_exceeds_quota():
    """예약석은 상한이기도 하다 — github 점수가 아무리 높아도 5건을 넘지 않는다."""
    arts = _arts("github", 30, 9999) + _arts("hackernews", 30, 100)
    got = pick(arts, top_n=20, per_source=15, quota=QUOTA)
    assert _counts(got)["github"] == 5
    assert len(got) == 20


def test_short_reserved_is_not_backfilled_even_with_room():
    """일반 출처에 자리와 후보가 남아 있어도 예약석을 대신 채우지 않는다.

    per_source가 커서 일반이 더 들어올 수 있는 상황 — 예전 코드는 여기서
    top_n까지 채워 20건을 만들었다.
    """
    arts = _arts("hackernews", 30, 900) + _arts("github", 4, 100)
    got = pick(arts, top_n=20, per_source=30, quota=QUOTA)
    assert len(got) == 19
    assert _counts(got) == {"hackernews": 15, "github": 4}


def test_general_shortage_does_not_break():
    arts = _arts("hackernews", 3, 900) + _arts("github", 10, 100)
    got = pick(arts, top_n=20, per_source=15, quota=QUOTA)
    assert _counts(got) == {"hackernews": 3, "github": 5}


def test_general_slots_respect_per_source_cap():
    arts = _arts("hackernews", 30, 900) + _arts("devto", 30, 800) + _arts("github", 10, 100)
    got = pick(arts, top_n=20, per_source=5, quota=QUOTA)
    counts = _counts(got)
    assert counts["github"] == 5
    assert counts["hackernews"] <= 5 and counts["devto"] <= 5


def test_without_quota_behaves_as_before():
    arts = _arts("hackernews", 30, 900)
    assert len(pick(arts, top_n=20, per_source=20, quota={})) == 20
    assert len(pick(arts, top_n=20, per_source=20, quota=None)) == 20


def test_quota_larger_than_top_n():
    arts = _arts("github", 30, 100)
    got = pick(arts, top_n=3, per_source=5, quota={"github": 5})
    assert len(got) <= 3


def test_empty_input():
    assert pick([], top_n=20, per_source=5, quota=QUOTA) == []
