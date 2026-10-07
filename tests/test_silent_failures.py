"""수집기가 에러 없이 조용히 덜 가져오던 자리들 (2026-10-07 점검).

- lobsters·geeknews 가 선별 상한(per_source 5)을 수집 개수로 읽어 5건씩만 받았다
- dev.to 가 동시 4개 요청에 429 를 받아 태그째 사라졌다 (3주 132회)
- 날짜를 못 읽은 기사가 기간 필터를 그대로 통과했다
- 해커뉴스 개별 글 요청 실패가 아무 흔적 없이 버려졌다
"""
import time
from datetime import datetime, timezone

import build
from news.core.common import published
from news.core.filters import recent_only
from news.scrapers import devto, geeknews, github, hackernews, lobsters, rss, trendshift


# ── 수집 개수 설정 ─────────────────────────────────────────

def _stub_scrapers(monkeypatch, seen):
    for mod in (hackernews, github, trendshift, devto, rss):
        monkeypatch.setattr(mod, "fetch", lambda *a, **k: [])
    monkeypatch.setattr(lobsters, "fetch", lambda limit=25: seen.setdefault("lobsters", limit) and [])
    monkeypatch.setattr(geeknews, "fetch", lambda limit=25, **k: seen.setdefault("geeknews", limit) and [])


def test_lobsters_긱뉴스는_수집_개수를_per_source_fetch로_읽는다(monkeypatch):
    seen: dict = {}
    _stub_scrapers(monkeypatch, seen)
    cfg = {"scraper": {"per_source": 5, "per_source_fetch": 40},
           "sources": {"anthropic": False}}
    build.run_scrapers(cfg, {}, {})
    assert seen == {"lobsters": 40, "geeknews": 40}


def test_per_source_fetch가_없으면_30이다(monkeypatch):
    """per_source(선별 상한 5)로 떨어지면 안 된다 — 그게 원래 버그였다."""
    seen: dict = {}
    _stub_scrapers(monkeypatch, seen)
    build.run_scrapers({"scraper": {"per_source": 5}, "sources": {"anthropic": False}}, {}, {})
    assert seen == {"lobsters": 30, "geeknews": 30}


# ── dev.to 429 ────────────────────────────────────────────

class _Resp:
    def __init__(self, code, body=None, headers=None):
        self.status_code, self._body, self.headers = code, body or [], headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"{self.status_code} Client Error", response=self)

    def json(self):
        return self._body


_POST = {"url": "https://dev.to/a/1", "title": "t", "published_at": "2026-10-07T01:00:00Z"}


def test_devto_429면_Retry_After만큼_쉬고_한_번_다시_묻는다(monkeypatch):
    answers = [_Resp(429, headers={"Retry-After": "7"}), _Resp(200, [_POST])]
    slept = []
    monkeypatch.setattr(devto.http, "get", lambda *a, **k: answers.pop(0))
    monkeypatch.setattr(devto.time, "sleep", slept.append)
    got = devto._one("go", 10)
    assert [g["url"] for g in got] == [_POST["url"]]
    assert slept == [7]


def test_devto_Retry_After가_너무_길면_상한까지만_쉰다(monkeypatch):
    answers = [_Resp(429, headers={"Retry-After": "3600"}), _Resp(429)]
    slept = []
    monkeypatch.setattr(devto.http, "get", lambda *a, **k: answers.pop(0))
    monkeypatch.setattr(devto.time, "sleep", slept.append)
    assert devto._one("go", 10) is None          # 두 번째도 429 → 실패
    assert slept == [devto.RETRY_AFTER_MAX]


def test_devto_실패한_태그를_태그별_건수로_남긴다(monkeypatch, capsys):
    """태그 하나가 계속 429 면 devto 총계는 40건이라 아무 신호가 없다.
    rss 가 피드별로 세듯 태그별로 세면 출처 침묵 알림이 그 태그를 잡는다."""
    def get(url, params=None, **k):
        return _Resp(429) if params["tag"] == "go" else _Resp(200, [{**_POST, "url": params["tag"]}])
    monkeypatch.setattr(devto.http, "get", get)
    monkeypatch.setattr(devto.time, "sleep", lambda s: None)
    counts: dict = {}
    got = devto.fetch(tags=["python", "go", "rust"], counts=counts)
    assert [a["tag"] for a in got] == ["python", "rust"]
    assert counts == {"devto:python": 1, "devto:go": 0, "devto:rust": 1}
    assert "1개" in capsys.readouterr().out


def test_devto_동시_요청은_두_개까지다(monkeypatch):
    import threading
    live, peak, lock = [0], [0], threading.Lock()

    def get(*a, **k):
        with lock:
            live[0] += 1
            peak[0] = max(peak[0], live[0])
        time.sleep(0.02)
        with lock:
            live[0] -= 1
        return _Resp(200, [])
    monkeypatch.setattr(devto.http, "get", get)
    devto.fetch(tags=[str(i) for i in range(8)])
    assert peak[0] <= 2


# ── 날짜 ──────────────────────────────────────────────────

def test_published는_못_읽은_날짜를_표시한다():
    assert published("Wed, 07 Oct 2026 12:00:00 GMT")["published_at"]
    assert published(None) == {"published_at": None}
    assert published("") == {"published_at": None}
    bad = published("어제 오후")
    assert bad == {"published_at": None, "date_unparsed": "어제 오후"}


def _now():
    return datetime.now(timezone.utc).timestamp()


def test_날짜가_원래_없는_출처는_통과한다():
    """GitHub 트렌딩·Trendshift 는 게시 시각 개념이 없다. 여기서 빠지면 예약석 5칸이 빈다.
    Anthropic engineering 맨 위 특집 카드도 목록에 날짜가 없다."""
    arts = [{"source": "github", "url": "g", "published_at": None},
            {"source": "github", "feed": "Trendshift", "url": "t", "published_at": None},
            {"source": "anthropic", "feed": "Anthropic Engineering", "url": "a", "published_at": None}]
    assert [a["url"] for a in recent_only(arts, 48)] == ["g", "t", "a"]


def test_날짜를_못_읽은_기사는_버리고_건수를_남긴다(capsys):
    arts = [{"source": "rss", "url": "bad", "published_at": None, "date_unparsed": "어제 오후"},
            {"source": "devto", "url": "garbage", "published_at": "not-a-date"},
            {"source": "rss", "url": "ok", "published_at": _now()}]
    assert [a["url"] for a in recent_only(arts, 48)] == ["ok"]
    assert "날짜를 못 읽은 2건" in capsys.readouterr().out


class _Text:
    def __init__(self, text):
        self.text = text
        self.content = text.encode()
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        import json
        return json.loads(self.text)


def test_수집기별_날짜_필드(monkeypatch):
    """어떤 수집기가 날짜를 비우고 어떤 수집기가 못 읽은 날짜를 표시하는지 고정한다."""
    # GitHub 트렌딩: 날짜 없음, 표시 없음
    gh = ('<article class="Box-row"><h2><a href="/o/r">o / r</a></h2><p>d</p>'
          '<span class="d-inline-block float-sm-right">12 stars today</span></article>')
    monkeypatch.setattr(github.http, "get", lambda *a, **k: _Text(gh))
    g = github.fetch()[0]
    assert g["published_at"] is None and "date_unparsed" not in g

    # RSS: pubDate 가 있는데 못 읽으면 표시
    feed = ('<?xml version="1.0"?><rss><channel><item><title>T</title><link>https://x/1</link>'
            '<pubDate>어제 오후</pubDate></item><item><title>U</title><link>https://x/2</link>'
            '</item></channel></rss>')
    monkeypatch.setattr(rss.http, "get", lambda *a, **k: _Text(feed))
    bad, missing = rss._one({"url": "https://x/feed", "name": "x"}, 8)
    assert bad["date_unparsed"] == "어제 오후"
    assert missing["published_at"] is None and "date_unparsed" not in missing

    # lobsters·dev.to 도 같은 규칙
    monkeypatch.setattr(lobsters.http, "get", lambda *a, **k: _Text(
        '[{"title":"t","url":"https://l/1","created_at":"garbage"}]'))
    assert lobsters.fetch()[0]["date_unparsed"] == "garbage"
    monkeypatch.setattr(devto.http, "get", lambda *a, **k: _Resp(200, [{**_POST, "published_at": "??"}]))
    assert devto._one("go", 10)[0]["date_unparsed"] == "??"
    monkeypatch.setattr(devto.http, "get", lambda *a, **k: _Resp(200, [_POST]))
    assert isinstance(devto._one("go", 10)[0]["published_at"], float)


# ── 해커뉴스 ──────────────────────────────────────────────

def test_해커뉴스_개별_글_실패를_한_줄로_남긴다(monkeypatch, capsys):
    def get(url, **k):
        if url.endswith("topstories.json"):
            return _Text("[1, 2, 3]")
        if url.endswith("/2.json"):
            raise OSError("timeout")
        return _Text('{"id": %s, "type": "story", "title": "t", "time": 1}' % url.rsplit("/", 1)[1][:-5])
    monkeypatch.setattr(hackernews.http, "get", get)
    got = hackernews.fetch(limit=3)
    assert len(got) == 2
    assert "[hackernews] 글 3건 중 1건 요청 실패" in capsys.readouterr().out
