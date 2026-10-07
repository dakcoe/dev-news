"""긱뉴스 글과 해커뉴스 글이 같은 원문이면 한 번만 실린다.

긱뉴스 피드의 <link>는 긱뉴스 글 주소라 원문 주소와 절대 안 맞고, 한국어 제목과
영어 제목은 낱말도 안 겹친다. 2026-09-22~23 네 회차에서 같은 소식 두 줄 9쌍 중
6쌍이 이 경우였다.
"""
import json

from news.core import seen as S
from news.core.dedup import merge_duplicates, normalize_url
from news.scrapers import geeknews

GN = {"title": "워터마크가 아니라 스파이마크", "url": "https://news.hada.io/topic?id=34104",
      "origin_url": "https://brand.io/article/spymarks/", "source": "geeknews", "score": 1}
HN = {"title": "Spymarks, Not Watermarks", "url": "https://brand.io/article/spymarks",
      "source": "hackernews", "score": 50}


class _Resp:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


def test_글_페이지의_제목_링크가_원문이다(monkeypatch):
    html = ('<div class="topictitle link"><a class="bold ud topic-title-link" '
            'href="https://brand.io/article/spymarks/">t</a></div>'
            '<h6><a href="https://news.ycombinator.com/item?id=1">HN</a></h6>')
    monkeypatch.setattr(geeknews.http, "get", lambda *a, **k: _Resp(html))
    assert geeknews.origin_url(GN["url"]) == "https://brand.io/article/spymarks/"


def test_원문이_긱뉴스_자신이면_없다(monkeypatch):
    html = '<a class="topic-title-link" href="https://news.hada.io/topic?id=1">Show GN</a>'
    monkeypatch.setattr(geeknews.http, "get", lambda *a, **k: _Resp(html))
    assert geeknews.origin_url(GN["url"]) is None


def test_페이지를_못_읽으면_없다(monkeypatch):
    def boom(*a, **k):
        raise OSError("403")
    monkeypatch.setattr(geeknews.http, "get", boom)
    assert geeknews.origin_url(GN["url"]) is None


def test_같은_회차에_오면_하나로_묶는다():
    out = merge_duplicates([GN, HN])
    assert len(out) == 1
    assert out[0]["source"] == "hackernews"          # 점수가 높은 쪽이 대표
    assert GN["url"] in out[0]["merged_urls"]        # 긱뉴스 주소도 seen 에 남는다


def test_긱뉴스만_실린_뒤_해커뉴스가_오면_이미_본_것이다(tmp_path):
    lone = merge_duplicates([GN])[0]
    p = str(tmp_path / "seen.json")
    S.mark_seen([lone], p)
    assert S.filter_unseen([HN], p) == []


def test_해커뉴스가_먼저_실리면_긱뉴스는_이미_본_것이다(tmp_path):
    p = tmp_path / "seen.json"
    p.write_text(json.dumps({HN["url"]: "2026-09-22T00:00:00+00:00"}), encoding="utf-8")
    assert S.filter_unseen([GN], str(p)) == []


def test_저장소_첫_화면의_브랜치_주소는_저장소_주소와_같다():
    assert normalize_url("https://github.com/o/kev/tree/main") == normalize_url("https://github.com/o/kev")
    # 하위 경로가 붙으면 다른 내용이다
    assert normalize_url("https://github.com/o/kev/tree/main/docs") != normalize_url("https://github.com/o/kev")


_FEED = ("<?xml version='1.0' encoding='UTF-8'?><feed xmlns='http://www.w3.org/2005/Atom'>"
         + "".join(f"<entry><title>글 {i}</title><link rel='alternate' href='https://news.hada.io/topic?id={i}'/>"
                   "<published>2026-10-07T22:42:53+09:00</published><content>c</content></entry>"
                   for i in range(5))
         + "</feed>")


class _Status:
    def __init__(self, code, text=""):
        self.status_code, self.text = code, text

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"{self.status_code} Client Error", response=self)


def test_글_페이지가_막히면_나머지는_묻지_않고_건수를_남긴다(monkeypatch, capsys):
    """2026-09-30부터 news.hada.io 글 페이지가 브라우저가 아닌 요청에 전부 403이다
    (피드와 robots.txt 는 200). 그대로 두면 회차마다 30번 403을 받고 원문 주소는
    조용히 사라진다. 첫 요청이 막히면 그만 묻고, 찾은 원문 수를 출처 건수로 남겨
    연속 0건이면 출처 침묵 알림으로 드러나게 한다."""
    calls = []

    def get(url, **k):
        calls.append(url)
        return _Status(200, _FEED) if "/rss/" in url else _Status(403, "Forbidden")
    monkeypatch.setattr(geeknews.http, "get", get)
    counts: dict = {}
    got = geeknews.fetch(limit=30, counts=counts)
    assert len(got) == 5
    assert counts == {"geeknews:원문": 0}
    assert len([u for u in calls if "topic?id=" in u]) == 1
    out = capsys.readouterr().out
    assert "403" in out and "4건" in out


def test_원문을_찾은_수를_센다(monkeypatch):
    page = '<a class="topic-title-link" href="https://brand.io/a">t</a>'

    def get(url, **k):
        return _Status(200, _FEED if "/rss/" in url else page)
    monkeypatch.setattr(geeknews.http, "get", get)
    counts: dict = {}
    got = geeknews.fetch(limit=30, counts=counts)
    assert counts == {"geeknews:원문": 5}
    assert all(a["origin_url"] == "https://brand.io/a" for a in got)
