"""Claude 제품 블로그(claude.com/blog)와 개발자 블로그(claude.dev RSS)도 Anthropic 출처로 받는다.

개발자용 글은 claude.dev 에만 올라와서, 빠뜨리면 HN 에 누가 올려야만 실렸다.
"""
from news.scrapers import anthropic as A


class _R:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


def test_제목이_속성에만_있는_카드를_읽는다(monkeypatch):
    html = ('<a data-cta-copy="Claude Code now supports artifacts" href="/blog/artifacts-in-claude-code">'
            '<span>Read more</span></a><a href="/blog">all</a>')
    monkeypatch.setattr(A.http, "get", lambda *a, **k: _R(html))
    got = A._fetch_page("https://claude.com", "/blog", "/blog/", "Claude 블로그", "data-cta-copy", 8)
    assert [(g["title"], g["url"], g["source"]) for g in got] == [
        ("Claude Code now supports artifacts", "https://claude.com/blog/artifacts-in-claude-code", "anthropic")]


def test_개발자_블로그_RSS를_읽는다(monkeypatch):
    rss = ('<?xml version="1.0"?><rss><channel><item><title>Building with Claude Sonnet 5.5</title>'
           '<link>https://claude.dev/blog/building-with-claude-sonnet-5-5/</link>'
           '<pubDate>Tue, 29 Sep 2026 12:00:00 GMT</pubDate><description>&lt;p&gt;How to&lt;/p&gt;</description>'
           '</item></channel></rss>')
    monkeypatch.setattr(A.http, "get", lambda *a, **k: _R(rss))
    got = A._fetch_rss("https://claude.dev/rss.xml", "Claude 개발자 블로그", 8)
    assert got[0]["title"] == "Building with Claude Sonnet 5.5"
    assert got[0]["feed"] == "Claude 개발자 블로그" and got[0]["published_at"]
