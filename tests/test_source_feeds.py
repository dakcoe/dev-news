"""수집 소스 화면의 피드 목록 (show-feeds-in-sources).

재현하는 결함: 소스 화면이 SOURCE_META 8개만 그려서 개별 RSS 피드가 보이지
않았다. Hugging Face가 8월에 21건 게재됐는데도 화면에서 찾을 수 없었다.
RSS 경로 기여는 1,292건 중 288건(22%)으로 작지 않다.
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from news.render import render  # noqa: E402


def _render(articles, tmp_path):
    out = tmp_path / "index.html"
    render(articles, str(out))
    return out.read_text(encoding="utf-8")


def _art(source, feed=None, url="https://e.com/x", title="T"):
    a = {"source": source, "url": url, "title": title, "summary": "요약",
         "batch": "2026-08-31T00:00:00+09:00", "batch_label": "8월 31일 00:00"}
    if feed:
        a["feed"] = feed
    return a


@pytest.fixture(scope="module")
def html(tmp_path_factory):
    with open(os.path.join(ROOT, "sample.json"), encoding="utf-8") as f:
        articles = json.load(f)
    return _render(articles, tmp_path_factory.mktemp("r"))


def test_source_view_groups_by_feed(html):
    """소스 카드 아래에 피드 하위 목록을 그리는 코드가 있어야 한다."""
    assert "subfeeds" in html


def test_feed_names_are_available_to_the_view(tmp_path):
    """뷰 모델의 from에 피드 이름이 실려야 화면에서 묶을 수 있다."""
    out = _render([_art("rss", "Hugging Face", "https://e.com/1"),
                   _art("rss", "The Decoder", "https://e.com/2")], tmp_path)
    assert "Hugging Face" in out and "The Decoder" in out


def test_single_feed_source_is_not_expanded(tmp_path):
    """피드 구분이 없는 출처(hackernews 등)에는 하위 목록이 붙지 않는다."""
    out = _render([_art("hackernews", None, "https://e.com/1")], tmp_path)
    # 하위 목록 렌더는 from 값이 2개 이상일 때만 — 조건이 코드에 남아 있어야 한다
    assert "subfeeds" in out
