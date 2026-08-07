"""corpus-feeds-page-exclusion 회귀 테스트.

코퍼스 축적용 피드(page: false)는 candidates 기록까지만 하고 페이지 선별에서는
제외한다 (SPEC 1.1 "후보를 넓게 기록하는 것과 페이지에 뭘 싣는가는 별개다").
r/LocalLLaMA 밈 게시물("Friday humor")이 rss 기본점수를 업고 페이지에 실린 사고의 재발 방지.
"""
import os
from unittest.mock import MagicMock, patch

import yaml

import build
from news.scrapers import rss

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FAKE_FEED_XML = b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item>
    <title>Friday humor</title>
    <link>https://example.test/meme</link>
    <description>submitted by /u/someone</description>
    <pubDate>Fri, 07 Aug 2026 00:00:00 GMT</pubDate>
  </item>
</channel></rss>
"""


def _fake_response():
    resp = MagicMock()
    resp.content = FAKE_FEED_XML
    resp.raise_for_status = MagicMock()
    return resp


def test_rss_page_false_propagates():
    with patch.object(rss.requests, "get", return_value=_fake_response()):
        items = rss._one({"name": "r/Test", "url": "https://example.test/.rss",
                          "page": False}, limit=8)
    assert items and all(a["page"] is False for a in items)


def test_rss_page_defaults_true():
    with patch.object(rss.requests, "get", return_value=_fake_response()):
        items = rss._one({"name": "Blog", "url": "https://example.test/feed"}, limit=8)
    assert items and all(a["page"] is True for a in items)


def test_page_eligible_filters_corpus_items():
    arts = [
        {"title": "실린다", "page": True},
        {"title": "코퍼스 전용", "page": False},
        {"title": "플래그 없음(타 소스)"},
    ]
    kept = build.page_eligible(arts)
    assert [a["title"] for a in kept] == ["실린다", "플래그 없음(타 소스)"]


def test_config_corpus_feeds_marked():
    with open(os.path.join(ROOT, "config.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    feeds = {f["name"]: f for f in cfg["feeds"]}
    for name in ("arXiv cs.AI", "arXiv cs.CL", "r/LocalLLaMA"):
        assert feeds[name].get("page") is False, f"{name}는 코퍼스 전용이어야 한다"
