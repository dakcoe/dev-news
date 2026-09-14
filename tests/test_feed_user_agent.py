"""피드별 User-Agent 지정 (per-feed-user-agent).

재현하는 결함: consolidate-http에서 UA를 하나로 통일하면서 r/LocalLLaMA RSS가
429로 막혔다. 실측 — 옛 UA는 200, 새 공용 UA와 무작위 UA는 둘 다 429.
레딧이 처음 보는 UA에 즉시 429를 준다.
"""
import os
import sys
from unittest.mock import MagicMock, patch

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from news.scrapers import rss  # noqa: E402

FEED_XML = b"""<?xml version='1.0'?><rss><channel>
<item><title>T</title><link>https://e.com/a</link><pubDate>Wed, 20 Aug 2026 12:00:00 +0000</pubDate></item>
</channel></rss>"""


def _resp():
    r = MagicMock()
    r.status_code = 200
    r.content = FEED_XML
    r.text = FEED_XML.decode()
    return r


def _headers_used(feed):
    with patch.object(rss.http, "get", return_value=_resp()) as g:
        rss.fetch([feed], per_feed=3)
    return g.call_args.kwargs.get("headers")


def test_feed_user_agent_is_passed():
    headers = _headers_used({"name": "r/LocalLLaMA", "url": "https://e.com/f.rss",
                             "user_agent": "legacy-ua/1.0"})
    assert headers["User-Agent"] == "legacy-ua/1.0"


def test_without_setting_uses_shared_ua():
    """지정하지 않은 피드는 공용 UA를 그대로 쓴다 — http.get이 기본값을 붙인다."""
    assert not _headers_used({"name": "OpenAI", "url": "https://e.com/f.rss"})


def test_override_does_not_leak_to_other_feeds():
    calls = {}

    def fake_get(url, **kw):
        calls[url] = kw.get("headers")
        return _resp()

    with patch.object(rss.http, "get", side_effect=fake_get):
        rss.fetch([
            {"name": "A", "url": "https://a.com/f.rss", "user_agent": "legacy/1.0"},
            {"name": "B", "url": "https://b.com/f.rss"},
        ], per_feed=3)
    assert calls["https://a.com/f.rss"]["User-Agent"] == "legacy/1.0"
    assert not calls["https://b.com/f.rss"]


def test_모든_수집기가_공용_http를_쓴다():
    """공용 http.get은 5xx에 재시도한다. 직접 requests.get을 부르면 순간 502 한
    번에 그 회차 몫이 통째로 빈다 — 예외가 아니라 0건이라 침묵 경고도 3회차
    연속돼야 뜬다. github와 trendshift가 그 상태였다.

    POST는 보지 않는다. 공용 http에는 get만 있다.
    """
    import glob
    import re
    bad = []
    for path in glob.glob(os.path.join(ROOT_DIR, "news", "scrapers", "*.py")):
        src = open(path, encoding="utf-8").read()
        if re.search(r"^\s*resp\s*=\s*requests\.get\(", src, re.M):
            bad.append(os.path.basename(path))
    assert not bad, f"공용 http를 안 쓰는 수집기: {bad}"


def test_브라우저_위장을_쓰지_않는다():
    """정직하게 밝힌다. 상대가 막을 근거를 주는 편이 낫고, 차단당하면
    fetch_health에 남아 진단이 된다 (news/core/http.py의 방침)."""
    import glob
    bad = []
    for path in glob.glob(os.path.join(ROOT_DIR, "news", "scrapers", "*.py")):
        src = open(path, encoding="utf-8").read()
        if "Mozilla/5.0" in src:
            bad.append(os.path.basename(path))
    assert not bad, f"브라우저 위장이 남아 있다: {bad}"
