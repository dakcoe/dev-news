"""Claude 제품 블로그(claude.com/resources/articles, 옛 /blog)와 개발자 블로그(claude.dev RSS)도 Anthropic 출처로 받는다.

개발자용 글은 claude.dev 에만 올라와서, 빠뜨리면 HN 에 누가 올려야만 실렸다.
"""
from news.scrapers import anthropic as A


class _R:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


# 2026-10-07 claude.com/resources/articles 목록의 카드 구조를 그대로 옮겼다.
# 날짜가 제목보다 앞에 오고, 설명이 제목보다 길다.
_LISTING = (
    '<a href="/resources/articles/claude-now-works-in-google-docs-sheets-and-slides">'
    '<div>Article</div><div>Oct 6, 2026</div>'
    '<h3>Claude now works with Google Docs, Sheets, and Slides</h3>'
    '<p>Teams that run on Google Workspace can now bring Claude into their files or work on their files '
    'directly from Claude, with our new add-on and connectors (in beta).</p><div>Claude Enterprise</div></a>'
    '<a href="/resources/articles/claude-now-works-in-google-docs-sheets-and-slides">'
    '<div>Article</div><div>Oct 6, 2026</div>'
    '<h3>Claude now works with Google Docs, Sheets, and Slides</h3></a>'
    '<a href="/resources/articles/no-date-card"><div>Article</div><h3>A card without a date</h3></a>'
    '<a href="/blog/old-style-post"><div>Sep 30, 2026</div><h3>An old style blog address</h3></a>'
    '<a href="https://claude.com/resources/articles/absolute-link"><div>Oct 1, 2026</div>'
    '<h3>Customize Claude Code with mods</h3></a>'
    '<a href="/resources/articles">Articles</a>'
)


def test_제품_블로그는_목록_페이지_한_장에서_읽는다(monkeypatch):
    """글이 claude.com/blog 에서 /resources/articles 로 옮겨 가며 사이트맵에서
    lastmod 가 사라졌다. 사이트맵 방식은 0건이 됐고, 256개 글 페이지를 매번 받을 수는
    없다. 목록 카드에 날짜와 제목이 다 있어 요청 한 번이면 된다."""
    calls = []

    def get(url, **k):
        calls.append((url, (k.get("headers") or {}).get("Accept-Language", "")))
        return _R(_LISTING)
    monkeypatch.setattr(A.http, "get", get)
    got = A._fetch_claude_blog(8)
    # 공용 http 의 기본값(ko)으로 물으면 /ko/ 로 넘어가 링크가 하나도 안 걸린다
    assert len(calls) == 1 and calls[0][0] == "https://claude.com/resources/articles"
    assert calls[0][1].startswith("en")
    assert [(g["title"], g["url"]) for g in got] == [
        ("Claude now works with Google Docs, Sheets, and Slides",
         "https://claude.com/resources/articles/claude-now-works-in-google-docs-sheets-and-slides"),
        ("An old style blog address", "https://claude.com/blog/old-style-post"),
        ("Customize Claude Code with mods", "https://claude.com/resources/articles/absolute-link"),
    ]
    assert all(g["published_at"] and g["source"] == "anthropic" and g["feed"] == "Claude 블로그"
               for g in got)


def test_날짜를_못_읽은_제품_블로그_카드는_받지_않는다(monkeypatch):
    """날짜 없는 글은 기간 필터에 걸리지 않으니, 옛 글이 새 글처럼 실린다."""
    monkeypatch.setattr(A.http, "get", lambda url, **k: _R(_LISTING))
    assert "no-date-card" not in " ".join(g["url"] for g in A._fetch_claude_blog(8))


def test_옮겨진_글은_옛_blog_주소로도_본_것으로_친다(monkeypatch):
    """claude-code-mods 같은 글이 /blog/ 주소로 이미 seen 에 들어가 있다. 새 주소만
    들고 오면 같은 글이 다시 실린다."""
    from news.core.dedup import url_keys
    monkeypatch.setattr(A.http, "get", lambda url, **k: _R(_LISTING))
    got = {g["url"]: g for g in A._fetch_claude_blog(8)}
    moved = got["https://claude.com/resources/articles/absolute-link"]
    assert "claude.com/blog/absolute-link" in " ".join(url_keys(moved))
    assert "origin_url" not in got["https://claude.com/blog/old-style-post"]


def test_특집_카드는_설명이_아니라_제목을_쓴다(monkeypatch):
    """engineering 목록의 맨 위 카드는 날짜 없이 제목과 긴 설명만 있다. 가장 긴 줄을
    제목으로 고르면 설명이 제목이 된다(2026-10-07 how-we-contain-claude)."""
    page = ('<a href="/engineering/how-we-contain-claude"><div>Featured</div>'
            '<h2>How we contain Claude across products</h2>'
            '<p>As agents grow more capable, so does their potential blast radius. The engineering '
            'question is how to cap it.</p></a>'
            '<a href="/engineering/april-23-postmortem"><h3>An update on recent Claude Code quality reports</h3>'
            '<div>Apr 23, 2026</div></a>'
            '<a href="/news/x"><div>Oct 2, 2026</div><span>Announcements</span>'
            '<span>Anthropic invests $100 million to train engineers</span></a>')
    monkeypatch.setattr(A.http, "get", lambda url, **k: _R(page))
    eng = A._fetch_page(A.BASE, "/engineering", "/engineering/", "Anthropic Engineering", 8)
    assert [g["title"] for g in eng] == ["How we contain Claude across products",
                                         "An update on recent Claude Code quality reports"]
    news = A._fetch_page(A.BASE, "/news", "/news/", "Anthropic", 8)
    assert news[0]["title"] == "Anthropic invests $100 million to train engineers"


def test_하위_수집원별로_센다(monkeypatch):
    """합계만 세면 Claude 블로그가 0건이 돼도 anthropic 총계는 24건이라 침묵 경고가
    뛰지 않는다. rss 가 피드별로 세는 것과 같은 모양으로 남긴다."""
    monkeypatch.setattr(A, "_fetch_page", lambda base, path, prefix, feed, limit:
                        [{"feed": feed}] * (2 if feed == "Anthropic" else 1))
    monkeypatch.setattr(A, "_fetch_claude_blog", lambda limit: [])
    monkeypatch.setattr(A, "_fetch_rss", lambda url, feed, limit: [{"feed": feed}] * 3)
    counts: dict = {}
    A.fetch(8, counts=counts)
    assert counts == {"anthropic:Anthropic": 2, "anthropic:Anthropic Engineering": 1,
                      "anthropic:Claude 블로그": 0, "anthropic:Claude 개발자 블로그": 3}


def test_개발자_블로그_RSS를_읽는다(monkeypatch):
    rss = ('<?xml version="1.0"?><rss><channel><item><title>Building with Claude Sonnet 5.5</title>'
           '<link>https://claude.dev/blog/building-with-claude-sonnet-5-5/</link>'
           '<pubDate>Tue, 29 Sep 2026 12:00:00 GMT</pubDate><description>&lt;p&gt;How to&lt;/p&gt;</description>'
           '</item></channel></rss>')
    monkeypatch.setattr(A.http, "get", lambda *a, **k: _R(rss))
    got = A._fetch_rss("https://claude.dev/rss.xml", "Claude 개발자 블로그", 8)
    assert got[0]["title"] == "Building with Claude Sonnet 5.5"
    assert got[0]["feed"] == "Claude 개발자 블로그" and got[0]["published_at"]
