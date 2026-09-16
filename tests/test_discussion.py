"""본문을 못 가져온 기사를 댓글로 메운다 (core/discussion.py).

9월 한 달 882건 중 69건이 요약 없이 실렸다. 같은 주소가 집에서는 멀쩡히
받아지는데 깃허브 러너의 IP 를 사이트가 막아서다. 댓글 API 는 막히지 않는다.
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from news.core import discussion as D  # noqa: E402
from news.core import http  # noqa: E402
from news import summarizer as S  # noqa: E402


class Resp:
    def __init__(self, data):
        self._d = data
    def json(self):
        return self._d


def stub_hn(monkeypatch, kids: dict):
    """kids: {id: item dict}. 글 1 의 자식은 kids 의 키 순서."""
    def fake_get(url, **kw):
        if url.endswith("/item/1.json"):
            return Resp({"id": 1, "kids": list(kids)})
        for k, v in kids.items():
            if url.endswith(f"/item/{k}.json"):
                return Resp(v)
        raise AssertionError(f"예상 밖 요청 {url}")
    monkeypatch.setattr(http, "get", fake_get)


HN = {"title": "t", "url": "https://blocked.example/post", "source": "hackernews",
      "discussion": "https://news.ycombinator.com/item?id=1", "content": ""}


def test_본문이_비면_댓글로_채운다(monkeypatch):
    stub_hn(monkeypatch, {10: {"text": "<p>첫 댓글 &amp; 내용</p>"}, 11: {"text": "둘째"}})
    out = D.fill_from_discussion([HN])[0]
    assert out["body_from"] == "comments"
    assert "[댓글 1] 첫 댓글 & 내용" in out["content"], "HTML 을 걷어내야 한다"
    assert "[댓글 2] 둘째" in out["content"]


def test_본문이_있으면_건드리지_않는다(monkeypatch):
    monkeypatch.setattr(http, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("요청하면 안 된다")))
    a = {**HN, "content": "실제 본문"}
    out = D.fill_from_discussion([a])[0]
    assert out is a and "body_from" not in out


def test_댓글이_없으면_그대로_둔다(monkeypatch):
    stub_hn(monkeypatch, {})
    out = D.fill_from_discussion([HN])[0]
    assert not out.get("content") and "body_from" not in out


def test_지워진_댓글은_건너뛰고_셋까지만(monkeypatch):
    kids = {10: {"deleted": True, "text": "x"}, 11: {"text": "a"}, 12: {"dead": True, "text": "y"},
            13: {"text": "b"}, 14: {"text": "c"}, 15: {"text": "d"}}
    stub_hn(monkeypatch, kids)
    out = D.fill_from_discussion([HN])[0]
    assert out["content"].count("[댓글 ") == 3
    assert "x" not in out["content"] and "y" not in out["content"]


def test_길이를_자른다(monkeypatch):
    stub_hn(monkeypatch, {10: {"text": "가" * 5000}, 11: {"text": "나" * 5000}, 12: {"text": "다" * 5000}})
    out = D.fill_from_discussion([HN])[0]
    assert len(out["content"]) <= D.MAX_TOTAL + 3 * 12   # 라벨 여유


def test_토론_주소가_없으면_주소로_검색한다(monkeypatch):
    a = {**HN}; del a["discussion"]
    calls = []
    def fake_get(url, **kw):
        calls.append(url)
        if "algolia" in url:
            return Resp({"hits": [{"objectID": "1"}]})
        if url.endswith("/item/1.json"):
            return Resp({"kids": [10]})
        return Resp({"text": "댓글"})
    monkeypatch.setattr(http, "get", fake_get)
    out = D.fill_from_discussion([a])[0]
    assert out.get("body_from") == "comments"
    assert any("algolia" in c and "blocked.example" in c for c in calls)


def test_로브스터스는_json_한_번으로(monkeypatch):
    a = {"title": "t", "url": "https://x/y", "source": "lobsters",
         "discussion": "https://lobste.rs/s/abc/title", "content": ""}
    monkeypatch.setattr(http, "get", lambda url, **k: Resp({"comments": [{"comment_plain": "ㄱ"}, {"comment_plain": "ㄴ"}]}) if url.endswith("/s/abc/title.json") else (_ for _ in ()).throw(AssertionError(url)))
    out = D.fill_from_discussion([a])[0]
    assert "[댓글 1] ㄱ" in out["content"] and "[댓글 2] ㄴ" in out["content"]


# ---------------- 프롬프트 ----------------

def test_댓글_본문이면_프롬프트에_밝힌다():
    body = S._body_for_prompt({"body_from": "comments"}, "[댓글 1] 어쩌고")
    assert body.startswith(S.COMMENTS_BODY)
    assert "기사 내용으로 단정하지 마라" in body


def test_보통_본문은_그대로_2천자():
    assert S._body_for_prompt({}, "x" * 3000) == "x" * 2000
    assert S._body_for_prompt({}, "") == S.NO_BODY


def test_두_프롬프트가_같은_헬퍼를_쓴다():
    src = open(os.path.join(ROOT, "news", "summarizer.py"), encoding="utf-8").read()
    assert src.count("_body_for_prompt(article, body)") == 2
    assert "(본문 없음 — 제목과 요약만으로" not in src


def test_스크레이퍼가_토론_주소를_남긴다():
    for name, needle in (("hackernews", '"discussion": f"https://news.ycombinator.com/item?id='),
                         ("lobsters", '"discussion": item.get("comments_url"')):
        src = open(os.path.join(ROOT, "news", "scrapers", f"{name}.py"), encoding="utf-8").read()
        assert needle in src, name


def test_빌드가_마스킹_앞에서_댓글을_채운다():
    src = open(os.path.join(ROOT, "build.py"), encoding="utf-8").read()
    assert 'redact_articles(fill_from_discussion(enrich(picked)), "본문")' in src


def test_화면이_댓글_기반임을_알린다():
    tpl = open(os.path.join(ROOT, "news", "template.html"), encoding="utf-8").read()
    assert "d.bodyFrom==='comments'" in tpl
    assert "bodyFrom:d.bodyFrom" in tpl and "bodyFrom:a.body_from" in tpl
    r = open(os.path.join(ROOT, "news", "render.py"), encoding="utf-8").read()
    assert '"bodyFrom": a.get("body_from")' in r
