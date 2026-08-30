"""죽은 category 필드 제거 (drop-dead-category).

scorer가 모든 기사에 category를 붙였지만 템플릿·렌더 어디에서도 읽지 않았다.
분포도 의미를 잃었다 — trending 1033 · hot_debate 226 · multi_source 13.
게다가 docs/data/articles/*.json에 실려 방문자마다 전송됐다.

cross_source_count는 다르다 — 점수 가산(* 300)에 실제로 쓰인다.
"""
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from news.core.scorer import score_and_categorize  # noqa: E402


def _art(url, source="hackernews", upvotes=100, comments=10, title="A headline here"):
    return {"url": url, "title": title, "source": source,
            "upvotes": upvotes, "comments": comments, "published_at": None}


def test_category_is_not_produced():
    out = score_and_categorize([_art("https://e.com/1")], top_n=10)
    assert "category" not in out[0]


def test_cross_source_count_survives():
    """점수 가산에 쓰이는 값이라 남아야 한다."""
    out = score_and_categorize([_art("https://e.com/1")], top_n=10)
    assert out[0]["cross_source_count"] >= 1


def test_merged_count_still_boosts_score():
    single = score_and_categorize([_art("https://e.com/1")], top_n=10)[0]
    merged = score_and_categorize(
        [{**_art("https://e.com/2"), "cross_source_count": 3}], top_n=10)[0]
    assert merged["score"] > single["score"], "cross_source_count 가산이 유지돼야 한다"


def test_score_is_still_computed():
    out = score_and_categorize([_art("https://e.com/1", upvotes=50, comments=4)], top_n=10)
    assert out[0]["score"] > 0


def test_top_n_still_applies():
    arts = [_art(f"https://e.com/{i}", upvotes=i, title=f"Headline number {i}")
            for i in range(10)]
    assert len(score_and_categorize(arts, top_n=3)) == 3
