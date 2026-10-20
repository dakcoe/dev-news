"""robots.txt 확인 (core/robots.py).

수집 코드에 robots.txt 확인이 없었다. 2026-10 게재 기사 862건 중 13건이 robots.txt 가
막은 페이지였고, 목록 요청 중 github.com/trending?since=daily·lobste.rs/hottest.json·
reddit RSS·the-decoder 피드가 막힌 주소였다.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from news.core import enrich, http  # noqa: E402
from news.core import robots as R  # noqa: E402
from news.core.fetch_health import reason_of  # noqa: E402
from news.scrapers import github, rss  # noqa: E402

# 실제 파일에서 가져온 규칙 (2026-10-21)
GITHUB = """
User-agent: baidu
crawl-delay: 1

User-agent: *
Allow: /*?tab=achievements&achievement=*
Disallow: /*?since=*
Disallow: /*&since=*
Disallow: /*/tree/
Disallow: /*.atom$
"""

LOBSTERS = """
User-agent: Applebot
User-agent: GoogleBot
Allow: /
Disallow: /search

Content-Signal: ai-input=no, ai-train=no, search=yes

User-agent: *
Crawl-delay: 1
Disallow: /
"""

DECODER = """
User-agent: *
Disallow: /wp-admin/
Disallow: */feed/
"""


# ---------------- 판정 ----------------

def test_와일드카드를_읽는다():
    assert not R.allowed_by(GITHUB, "https://github.com/trending?since=daily")
    assert not R.allowed_by(GITHUB, "https://github.com/trending?l=go&since=weekly")
    assert R.allowed_by(GITHUB, "https://github.com/trending")
    assert R.allowed_by(GITHUB, "https://github.com/trending?l=python")
    assert not R.allowed_by(GITHUB, "https://github.com/o/r/tree/main")


def test_끝_표시는_끝에서만_맞는다():
    assert not R.allowed_by(GITHUB, "https://github.com/o/r/commits.atom")
    assert R.allowed_by(GITHUB, "https://github.com/o/r/commits.atom?x=1")


def test_앞이_별인_규칙도_루트부터_맞는다():
    assert not R.allowed_by(DECODER, "https://the-decoder.com/feed/")
    assert not R.allowed_by(DECODER, "https://the-decoder.com/some-post/feed/")
    assert R.allowed_by(DECODER, "https://the-decoder.com/some-post/")


def test_이름이_맞는_묶음이_없으면_별_묶음():
    assert not R.allowed_by(LOBSTERS, "https://lobste.rs/hottest.json")
    assert not R.allowed_by(LOBSTERS, "https://lobste.rs/rss")
    assert R.allowed_by(LOBSTERS, "https://lobste.rs/hottest.json", token="googlebot")


def test_이름이_맞는_묶음이_있으면_별_묶음은_안_본다():
    text = "User-agent: *\nDisallow: /\n\nUser-agent: dev-news\nDisallow: /private/\n"
    assert R.allowed_by(text, "https://e.com/a")
    assert not R.allowed_by(text, "https://e.com/private/x")


def test_가장_긴_규칙이_이기고_같으면_Allow():
    text = "User-agent: *\nDisallow: /a\nAllow: /a/b\n"
    assert R.allowed_by(text, "https://e.com/a/b/c")
    assert not R.allowed_by(text, "https://e.com/a/x")
    assert R.allowed_by("User-agent: *\nDisallow: /a\nAllow: /a\n", "https://e.com/a")


def test_빈_Disallow와_빈_파일은_전부_허용():
    assert R.allowed_by("User-agent: *\nDisallow:\n", "https://e.com/x")
    assert R.allowed_by("", "https://e.com/x")
    assert R.allowed_by("<html><body>Not Found</body></html>", "https://e.com/x")


# ---------------- robots.txt 응답 ----------------

class Resp:
    def __init__(self, code, body=b""):
        self.status_code = code
        self.content = body


def _serve(monkeypatch, answer):
    calls = []

    def fake(url, **kw):
        calls.append(url)
        r = answer(url)
        if isinstance(r, Exception):
            raise r
        return r
    monkeypatch.setattr(http, "get_capped", fake)
    return calls


def test_없으면_허용_서버_오류면_금지(monkeypatch):
    _serve(monkeypatch, lambda url: {
        "https://gone.example/robots.txt": Resp(404),
        "https://down.example/robots.txt": Resp(503),
        "https://busy.example/robots.txt": Resp(429),
        "https://off.example/robots.txt": http.requests.ConnectionError("x"),
    }[url])
    c = R.Checker()
    assert c.allowed("https://gone.example/a")
    assert not c.allowed("https://down.example/a")
    assert not c.allowed("https://busy.example/a")
    assert not c.allowed("https://off.example/a")


def test_사이트마다_한_번만_받는다(monkeypatch):
    calls = _serve(monkeypatch, lambda url: Resp(200, DECODER.encode()))
    c = R.Checker()
    assert c.allowed("https://the-decoder.com/a/")
    assert not c.allowed("https://the-decoder.com/feed/")
    assert c.allowed("https://the-decoder.com/b/")
    assert calls == ["https://the-decoder.com/robots.txt"]


# ---------------- 수집 ----------------

class Deny:
    def allowed(self, url):
        return False


def test_막힌_기사는_요청하지_않고_기사는_남긴다(monkeypatch):
    monkeypatch.setattr(http, "get_capped", lambda *a, **k: (_ for _ in ()).throw(AssertionError(a)))
    content, image, status, code = enrich._fetch_one("https://e.com/post", Deny())
    assert (content, image, status, code) == (None, None, "robots", None)
    assert reason_of(status, code, content) == "robots"


def test_enrich가_robots_판정을_거친다(monkeypatch):
    """enrich 는 robots.txt 부터 받고, 막힌 기사는 link_status 를 robots 로 둔다."""
    _serve(monkeypatch, lambda url: Resp(200, b"User-agent: *\nDisallow: /\n"))
    monkeypatch.setattr(enrich, "record", lambda rows: None)
    out = enrich.enrich([{"url": "https://e.com/post", "source": "hackernews"}])
    assert out[0]["link_status"] == "robots" and out[0]["content"] is None


def test_막힌_피드는_받지_않는다(monkeypatch):
    monkeypatch.setattr(rss.http, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError(a)))
    assert rss._one({"name": "D", "url": "https://the-decoder.com/feed/"}, 8, Deny()) == []


def test_깃허브_트렌딩은_since를_붙이지_않는다(monkeypatch):
    seen = {}

    def fake(url, **kw):
        seen["params"] = kw.get("params")
        raise http.requests.RequestException("stop")
    monkeypatch.setattr(github.http, "get", fake)
    github.fetch()
    assert "since" not in (seen["params"] or {})
