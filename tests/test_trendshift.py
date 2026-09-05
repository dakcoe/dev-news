"""Trendshift 일간 순위 파서 (add-trendshift-source).

홈페이지 SSR HTML의 카드 구조를 본뜬 합성 픽스처로 검사한다. 실제 페이지에는
같은 `/repositories/<id>` 링크가 "Live // Mentions" 블록에도 있는데, 그쪽은
Like 버튼이 없다 — 그걸로 순위 카드만 골라내야 한다.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from news.scrapers.trendshift import parse  # noqa: E402


def _card(name, stars, desc, badge=""):
    return (
        '<div><div><div><div><img alt="owl"/></div>'
        f'<a href="/repositories/1">{name}</a>{badge}</div>'
        f'<div><div><span><svg/><span>{stars}</span></span></div></div></div>'
        f'<p>{desc}</p>'
        '<div><button type="button"><span aria-hidden="true"><svg/></span>'
        f'<span>Like {name}, 0 likes</span><span aria-hidden="true">0</span></button>'
        '<button type="button"><span aria-hidden="true"><svg/></span>'
        f'<span>Bookmark {name}, 0 bookmarks</span><span aria-hidden="true">0</span></button></div></div>'
    )


MENTIONS = (
    '<div><h2>Live//Mentions</h2><p><a href="/repositories/9">zara/youtube-digest</a></p>'
    '<a href="https://x.com/x/status/1">@someone</a></div>'
)

PAGE = (
    "<html><body>" + MENTIONS + "<h2>Trending//Daily</h2>"
    + _card("Farama-Foundation/Shimmy", "442",
            "PettingZoo and Gymnasium bindings for popular RL environments")
    + _card("EvoMap/AutoResearch", "1,231", "Research agents from idea to paper",
            badge='<span>New 2026</span><span>Mentioned on</span>')
    + _card("owner/no-desc", "7", "")
    + "</body></html>"
)


def test_parses_ranking_cards_only():
    got = parse(PAGE)
    names = [a["title"] for a in got]
    assert names == ["Farama-Foundation / Shimmy", "EvoMap / AutoResearch", "owner / no-desc"]
    assert all("youtube-digest" not in n for n in names)


def test_item_shape_matches_github_trending():
    a = parse(PAGE)[0]
    assert a["url"] == "https://github.com/Farama-Foundation/Shimmy"
    assert a["source"] == "github"          # dedup·Δ·예약석이 github 항목으로 다루게
    assert a["feed"] == "Trendshift"        # 화면 라벨
    assert a["upvotes"] == 442
    assert a["comments"] == 0
    assert a["published_at"] is None
    assert a["description"] == "PettingZoo and Gymnasium bindings for popular RL environments"


def test_comma_number_and_badge_noise():
    a = parse(PAGE)[1]
    assert a["upvotes"] == 1231
    assert a["description"] == "Research agents from idea to paper"
    assert "New 2026" not in a["title"]


def test_missing_description_is_empty_string():
    assert parse(PAGE)[2]["description"] == ""


def test_limit():
    assert len(parse(PAGE, limit=2)) == 2


def test_empty_or_unrelated_html():
    assert parse("") == []
    assert parse("<html><body><p>nothing</p></body></html>") == []
