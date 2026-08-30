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
