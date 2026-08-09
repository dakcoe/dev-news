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
    assert ".thumb{" in html                 # 오른쪽 썸네일 카드
    assert '"status"' in html                # 상태 카드
    assert "bdg" not in html                 # NEW/HOT 뱃지 제거
    assert 'data-s="score"' not in html      # 점수순 정렬 제거
    assert ".row:hover .ck" in html          # 체크박스는 호버 시에만 노출


def test_github_delta_shown(html):
    assert "d.delta" in html                 # 점수 대신 스타 Δ 표시 (SPEC 1.5)


# ---- SPEC 2.4~2.5: 아카이브 검색·북마크 스냅샷 ----

def test_archive_search_wired(html):
    assert "data/search-index.json" in html
    assert "openArchived" in html


def test_saved_snapshot_migration(html):
    assert "savedMap" in html
    assert "typeof item === 'string'" in html   # URL 배열 → 객체 승격


# ---- apply-tag-facet-ui: 태그 패싯 사이드바(F) + 모바일 드로어(I) ----

def test_tag_facet_sidebar(html):
    assert 'id="facet"' in html                 # 그룹 패싯 사이드바
    assert "facetHTML" in html
    assert ".fill" in html                      # 분포 막대
    assert "tagchips" not in html               # 구 태그 칩 한 줄 제거


def test_tag_multi_select_persisted(html):
    assert "tagSel" in html                     # 다중 선택 Set
    assert "dev-news-tagsel" in html            # localStorage 저장 (SPEC 3.3)
    assert "dev-news-tagfilter" in html         # 구 단일 키 마이그레이션


def test_tag_drawer_mobile(html):
    assert 'id="tagbtn"' in html                # 좁은 화면용 "태그" 버튼
    assert "scrim" in html                      # 드로어 스크림
    assert "facet open" in html or "facet.open" in html or ".facet.open" in html


def test_facet_collapsible(html):
    assert 'id="tagfold"' in html               # 사이드바 접기 버튼
    assert "dev-news-facetfold" in html         # 접힘 상태 localStorage 유지
    assert "layout fc" in html or "'fc'" in html or '"fc"' in html or "fc'" in html


def test_tagbtn_below_sources_with_color(html):
    assert "tagcp" in html                      # 보라 강조 스타일
    assert ".tagcp{" in html
    assert "tagrow" in html                     # 소스 칩 줄 아래 전용 줄
    # 태그 버튼은 컨트롤 바(barHTML)·소스 칩 줄(chipsHTML) 안에는 없다
    bar_fn = html.split("function barHTML()")[1].split("function ")[0]
    chips_fn = html.split("function chipsHTML()")[1].split("function ")[0]
    assert "tagbtn" not in bar_fn
    assert "tagbtn" not in chips_fn
    # 렌더 순서: 소스 칩 다음에 tagrow
    assert "chipsHTML()+tagRowHTML()" in html.replace(" ", "")


def test_tag_json_has_label_and_group(html):
    import re
    m = re.search(r"const TAGS = (\{.*?\});", html)
    assert m, "TAGS 상수가 없음"
    tags = json.loads(m.group(1))
    assert tags["ai"]["label"]
    assert tags["ai"]["group"]
    groups = {v["group"] for v in tags.values()}
    assert len(groups) == 3                     # AI / 개발 / 그 외
