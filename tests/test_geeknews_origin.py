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
