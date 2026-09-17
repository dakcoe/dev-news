"""skills.sh 리더보드 스냅샷 (news/skills_catalog.py)."""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from news import skills_catalog as SC  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures")


def _fx(name):
    return open(os.path.join(FIX, name), encoding="utf-8").read()


def test_첫_화면_행을_읽는다():
    rows = SC.parse_rows(_fx("skills_home.html"))
    assert len(rows) == 20
    r = rows[0]
    assert r["rank"] == 1 and r["name"] == "find-skills"
    assert (r["owner"], r["repo"]) == ("vercel-labs", "skills")
    assert r["url"] == "https://www.skills.sh/vercel-labs/skills/find-skills"
    assert r["metric"] == 3_400_000


def test_상승_화면_행을_읽는다():
    rows = SC.parse_rows(_fx("skills_trending.html"))
    assert rows[0]["name"] == "ai-avatar-video" and rows[0]["metric"] == 40_800
    # 페이지 번호는 1, 5, 9… 로 비어 있다. 우리는 순서대로 매기고 원래 번호는 따로 둔다.
    assert [r["rank"] for r in rows[:3]] == [1, 2, 3]
    assert rows[1]["site_rank"] == 5


@pytest.mark.parametrize("text,n", [("3.4M", 3_400_000), ("40.8K", 40_800), ("917", 917), ("설치", None)])
def test_수치_읽기(text, n):
    assert SC._metric(text) == n


def test_지난_회차와_견줘_순위_변화를_붙인다():
    prev = [{"rank": 5, "name": "a", "owner": "o", "repo": "r"}]
    now = [{"rank": 2, "name": "a", "owner": "o", "repo": "r"}, {"rank": 3, "name": "b", "owner": "o", "repo": "r"}]
    out = SC.with_delta(now, prev)
    assert out[0]["prev"] == 5 and out[1]["prev"] is None


def test_행이_너무_적으면_기존_파일을_지킨다(tmp_path):
    out = tmp_path / "skills.json"
    out.write_text('{"trending":[{"rank":1,"name":"x","owner":"o","repo":"r"}],"top":[]}', encoding="utf-8")
    assert SC.build.__name__ == "build"
    with pytest.raises(RuntimeError):
        SC.build(str(out), fetch=lambda path: _fx("skills_home.html"))   # 20행 < MIN_ROWS


def test_sync_는_실패해도_회차를_죽이지_않는다(tmp_path, monkeypatch):
    out = tmp_path / "skills.json"
    out.write_text('{"keep":1}', encoding="utf-8")
    monkeypatch.setattr(SC, "fetch_page", lambda path: (_ for _ in ()).throw(RuntimeError("x")))
    assert SC.sync(str(out)) is False
    assert json.loads(out.read_text(encoding="utf-8")) == {"keep": 1}


def test_빌드가_호출한다():
    b = open(os.path.join(ROOT, "build.py"), encoding="utf-8").read()
    assert 'skills_catalog.sync(os.path.join(ROOT, "docs", "data", "skills.json"))' in b


def test_화면은_레일에서_수집_소스_자리를_쓴다():
    t = open(os.path.join(ROOT, "news", "template.html"), encoding="utf-8").read()
    assert 'data-v="skills"' in t and 'data-v="src"' not in t
    assert "view==='src'" not in t
    assert "npx skills add '+gh+' --skill '+r.name" in t
    assert "safeU(r.url)" in t, "순위표 주소도 남이 정하는 값처럼 다룬다"


def test_스킬_페이지의_설명을_읽는다():
    d = SC.parse_desc(_fx("skill_page_head.html"))
    assert d.startswith("Helps users discover and install agent skills")


def test_설명은_지난_스냅샷에서_이어받고_없는_것만_읽는다():
    prev = [{"rank": 1, "name": "a", "owner": "o", "repo": "r", "desc": "이미 있음"}]
    rows = [{"rank": 1, "name": "a", "owner": "o", "repo": "r", "url": SC.SITE + "/o/r/a"},
            {"rank": 2, "name": "b", "owner": "o", "repo": "r", "url": SC.SITE + "/o/r/b"}]
    calls = []
    def fake(path):
        calls.append(path); return '<html><head><meta name="description" content="새로 읽음"></head></html>'
    got = SC.fill_descs(rows, prev, fetch=fake)
    assert got == 1 and calls == ["/o/r/b"]
    assert rows[0]["desc"] == "이미 있음" and rows[1]["desc"] == "새로 읽음"


def test_한_회차에_읽는_설명_수에_상한이_있다():
    rows = [{"rank": i, "name": f"s{i}", "owner": "o", "repo": "r", "url": SC.SITE + f"/o/r/s{i}"} for i in range(10)]
    calls = []
    SC.fill_descs(rows, [], fetch=lambda p: (calls.append(p), "<html></html>")[1], limit=3)
    assert len(calls) == 3


def test_화면에_설명과_빈_변화칸(monkeypatch):
    t = open(os.path.join(ROOT, "news", "template.html"), encoding="utf-8").read()
    assert "class=\"skdesc\"" in t and "'<span class=\"skd none\"></span>'" in t
