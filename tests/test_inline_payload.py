"""초기 전송량 분할 회귀 테스트 (split-initial-payload).

body·why는 상세 패널 전용이라 목록·검색·필터가 쓰지 않는다. 그런데도 30일치
전 기사분이 index.html에 인라인돼 557KB가 됐다. 최근 N일만 싣고 나머지는
상세를 열 때 월별 샤드에서 가져온다.
"""
import os
import re
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from news.render import INLINE_DAYS, TEMPLATE, to_view_model  # noqa: E402

KST = timezone(timedelta(hours=9))


def _art(days_ago, url="https://a"):
    batch = (datetime.now(KST) - timedelta(days=days_ago)).isoformat()
    return {"url": url, "title": "T", "ko_title": "제목", "summary": "요약 문장이다.",
            "why": "중요한 이유.", "source": "rss", "batch": batch, "tags": ["ai"]}


def test_recent_articles_keep_body_and_why():
    vm = to_view_model([_art(0)], inline_days=3)[0]
    assert vm["body"] == "<p>요약 문장이다.</p>"
    assert vm["why"] == "중요한 이유."


def test_old_articles_drop_body_and_why():
    vm = to_view_model([_art(10)], inline_days=3)[0]
    assert "body" not in vm and "why" not in vm


def test_old_articles_keep_list_fields():
    """목록·검색·필터가 쓰는 필드는 나이와 무관하게 남는다."""
    vm = to_view_model([_art(10)], inline_days=3)[0]
    for key in ("title", "snip", "tags", "src", "url", "pub", "from", "month", "batchLabel"):
        assert key in vm, key
    assert vm["snip"] == "요약 문장이다."
    assert vm["month"] == vm["batch"][:7]


def test_boundary_is_inclusive():
    assert "body" in to_view_model([_art(2)], inline_days=3)[0]
    assert "body" not in to_view_model([_art(4)], inline_days=3)[0]


def test_inline_days_zero_keeps_everything():
    assert "body" in to_view_model([_art(999)], inline_days=0)[0]


def test_unknown_batch_stays_inline():
    """회차를 모르면 지연 로딩이 불가능하므로 안전하게 인라인한다."""
    a = _art(10)
    del a["batch"]
    assert "body" in to_view_model([a], inline_days=3)[0]


def test_client_falls_back_to_shard():
    """openDetail이 body 부재를 감지해 openArchived로 위임하는지."""
    html = open(TEMPLATE, encoding="utf-8").read()
    assert "d.body===undefined" in html
    assert re.search(r"if\(d\.body===undefined\)\{\s*openArchived\(d\.url, d\.month", html)
    # extra 병합이 없으면 지연 로딩분 상세만 메타가 빠진다
    assert "Object.assign({" in html
    assert "function openArchived(url, month, extra)" in html


def test_search_does_not_depend_on_body():
    """visible()의 검색 대상에 body가 들어가면 지연 로딩분이 검색에서 누락된다."""
    html = open(TEMPLATE, encoding="utf-8").read()
    search = re.search(r"a=a\.filter\(d=>\(d\.title.*?\)\.toLowerCase\(\)\.includes\(s\)\)", html)
    assert search and "d.body" not in search.group(0)


def test_default_window_is_small():
    assert 1 <= INLINE_DAYS <= 7
