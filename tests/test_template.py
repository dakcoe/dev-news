"""template.html 디자인 회귀 테스트.

page-design-tweaks 작업분: 뉴스 수집 가짜 버튼 제거, 레일 버튼 확대,
기사 상세 오버레이(왼쪽 흐림) 제거가 유지되는지 확인한다.
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from news.render import render  # noqa: E402


@pytest.fixture(scope="module")
def html(tmp_path_factory):
    with open(os.path.join(ROOT, "sample.json"), encoding="utf-8") as f:
        articles = json.load(f)
    out = tmp_path_factory.mktemp("render") / "index.html"
    render(articles, str(out))
    return out.read_text(encoding="utf-8")


def test_collect_button_removed(html):
    assert "stbtn" not in html


def test_status_stats_kept(html):
    # 상태 카드는 헤더 한 줄(hstats)로 강등됐지만 통계 자체는 유지 (SPEC 3.2)
    assert "최근 30일" in html
    assert "안 읽음" in html


def test_overlay_removed(html):
    assert 'id="ov"' not in html
    assert ".ov{" not in html
    assert "getElementById('ov')" not in html


def test_detail_panel_kept(html):
    assert 'id="dt"' in html
    assert "openDetail" in html


def test_rail_buttons_bigger(html):
    assert "width:74px" in html          # .rail
    assert "width:50px;height:50px" in html  # .rb


def test_unread_toggle_has_checkbox(html):
    assert 'id="unread"><span class="ckm">' in html
    assert ".cp .ckm{" in html


def test_no_scrollbar_layout_shift(html):
    assert "scrollbar-gutter:stable" in html


# ---- 카드 레이아웃 (사용자 피드백으로 고밀도 리스트에서 복원) ----

def test_card_layout_with_thumbnail(html):
    assert ".thumb{" in html                 # 오른쪽 썸네일 카드 복원
    assert '"bdg new"' in html               # NEW 뱃지 복원
    assert '"status"' in html                # 상태 카드 복원
    assert "bdg hot" not in html             # HOT 뱃지는 SPEC대로 제거 유지


def test_github_delta_shown(html):
    assert "d.delta" in html                 # 점수 대신 스타 Δ 표시 (SPEC 1.5)


# ---- SPEC 2.4~2.5: 아카이브 검색·북마크 스냅샷 ----

def test_archive_search_wired(html):
    assert "data/search-index.json" in html
    assert "openArchived" in html


def test_saved_snapshot_migration(html):
    assert "savedMap" in html
    assert "typeof item === 'string'" in html   # URL 배열 → 객체 승격
