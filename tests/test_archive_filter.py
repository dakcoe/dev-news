"""아카이브 검색 결과를 실제로 함수를 돌려서 본다.

기존 template 검사는 HTML 안에 문자열이 있는지만 봤다. 그래서 archMatches()
에 '안 읽음' 조건이 빠진 것을 잡지 못했다 — 같은 화면의 위 목록에서는 사라진
기사가 아래 아카이브 목록에는 남아 있었다 (2026-09-21 외부 검토).
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from news.render import render  # noqa: E402

RUNNER = os.path.join(ROOT, "tests", "js", "run_fn.mjs")
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    with open(os.path.join(ROOT, "sample.json"), encoding="utf-8") as f:
        articles = json.load(f)
    out = tmp_path_factory.mktemp("render") / "index.html"
    render(articles, str(out))
    return str(out)


def arch(page, **globals_):
    g = {"INDEX": [], "DATA": [], "q": "", "filter": "all", "tagSel": [],
         "days": 0, "unreadOnly": False, "read": []}
    g.update(globals_)
    r = subprocess.run(["node", RUNNER, page, "archMatches", json.dumps(g)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


IDX = [{"t": "Rust 1.90 릴리스", "u": "https://e.com/rust", "m": "2026-08",
        "s": "github", "g": ["language"], "d": "2026-08-21"},
       {"t": "Rust 타입 추론", "u": "https://e.com/infer", "m": "2026-08",
        "s": "hackernews", "g": ["language"], "d": "2026-08-22"}]


def test_검색어로_찾는다(page):
    got = arch(page, INDEX=IDX, q="rust")
    # 둘 다 제목에 걸려 점수가 같으면 최근 회차가 위다
    assert [e["u"] for e in got] == ["https://e.com/infer", "https://e.com/rust"]


def test_안_읽음이면_읽은_기사는_빠진다(page):
    """이게 빠져 있었다. 위 목록에서는 사라진 기사가 아래에 남았다."""
    got = arch(page, INDEX=IDX, q="rust", unreadOnly=True,
               read=["https://e.com/rust"])
    assert [e["u"] for e in got] == ["https://e.com/infer"]


def test_안_읽음이_꺼져_있으면_그대로_나온다(page):
    got = arch(page, INDEX=IDX, q="rust", read=["https://e.com/rust"])
    assert len(got) == 2


def test_이미_목록에_있는_기사는_빼고_보여준다(page):
    got = arch(page, INDEX=IDX, q="rust", DATA=["https://e.com/rust"])
    assert [e["u"] for e in got] == ["https://e.com/infer"]


def test_출처와_기간도_같이_걸린다(page):
    assert [e["u"] for e in arch(page, INDEX=IDX, q="rust", filter="github")] \
        == ["https://e.com/rust"]
    assert arch(page, INDEX=IDX, q="rust", days=1) == []
