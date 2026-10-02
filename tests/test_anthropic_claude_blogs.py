"""Claude 제품 블로그(claude.com/blog)와 개발자 블로그(claude.dev RSS)도 Anthropic 출처로 받는다.

개발자용 글은 claude.dev 에만 올라와서, 빠뜨리면 HN 에 누가 올려야만 실렸다.
"""
from news.scrapers import anthropic as A


class _R:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


def test_제품_블로그는_사이트맵과_글의_발행일로_읽는다(monkeypatch):
    """목록이 최신순이 아니라 5월 글이 10월에 실렸다. 발행일을 못 읽으면 받지 않는다."""
    from datetime import datetime, timedelta, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    old = (datetime.now(timezone.utc) - timedelta(days=60)).strftime("%Y-%m-%d")
    pages = {
        A.CLAUDE_SITEMAP: f"<url><loc>https://claude.com/blog/new</loc><lastmod>{today}T00:00:00Z</lastmod></url>"
                          f"<url><loc>https://claude.com/blog/nodate</loc><lastmod>{today}T00:00:00Z</lastmod></url>"
                          f"<url><loc>https://claude.com/blog/stale</loc><lastmod>{old}T00:00:00Z</lastmod></url>",
        "https://claude.com/blog/new": '<meta content="Claude Opus 5.5 | Claude by Anthropic" property="og:title"/>'
                                       '"datePublished": "Sep 24, 2026"',
        "https://claude.com/blog/nodate": '<meta content="No date | Claude by Anthropic" property="og:title"/>',
    }
    monkeypatch.setattr(A.http, "get", lambda url, **k: _R(pages[url]))
    got = A._fetch_claude_blog(8)
    assert [(g["title"], g["url"], g["source"]) for g in got] == [
        ("Claude Opus 5.5", "https://claude.com/blog/new", "anthropic")]
    assert got[0]["published_at"]


def test_개발자_블로그_RSS를_읽는다(monkeypatch):
    rss = ('<?xml version="1.0"?><rss><channel><item><title>Building with Claude Sonnet 5.5</title>'
           '<link>https://claude.dev/blog/building-with-claude-sonnet-5-5/</link>'
           '<pubDate>Tue, 29 Sep 2026 12:00:00 GMT</pubDate><description>&lt;p&gt;How to&lt;/p&gt;</description>'
           '</item></channel></rss>')
    monkeypatch.setattr(A.http, "get", lambda *a, **k: _R(rss))
    got = A._fetch_rss("https://claude.dev/rss.xml", "Claude 개발자 블로그", 8)
    assert got[0]["title"] == "Building with Claude Sonnet 5.5"
    assert got[0]["feed"] == "Claude 개발자 블로그" and got[0]["published_at"]
