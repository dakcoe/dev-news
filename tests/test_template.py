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


def test_bar_has_dropdowns_and_filter_button(html):
    """bar-dropdown-cleanup: 바 = 검색 + 필터(좌측·강조색) + 커스텀 드롭다운 + 안 읽음."""
    bar_fn = html.split("function barHTML()")[1].split("\nfunction ")[0]
    assert "ddHTML('sortsel'" in bar_fn         # 정렬 커스텀 드롭다운
    assert "ddHTML('daysel'" in bar_fn          # 기간 커스텀 드롭다운
    assert 'id="unread"' in bar_fn              # 안 읽음은 패널 밖
    assert 'id="tagbtn"' in bar_fn              # 필터 버튼은 바 안(검색 옆)
    assert "tagcp" in bar_fn and ".cp.tagcp{" in html   # .cp보다 특이도 높은 강조색
    assert ".ddpop{" in html and ".dditem{" in html   # 커스텀 드롭다운 스타일
    assert "<select" not in html                # 네이티브 select 미사용
    assert "tagRowHTML" not in html             # 전용 줄 제거


def test_panel_has_source_and_tags_only(html):
    facet_fn = html.split("function facetHTML()")[1].split("\nfunction ")[0]
    assert 'data-f="' in facet_fn               # 출처 목록
    assert 'data-ft=' in facet_fn               # 태그 목록
    assert 'data-fs=' not in facet_fn           # 정렬은 바로 이동
    assert 'data-fd=' not in facet_fn           # 기간은 바로 이동
    assert 'id="unread"' not in facet_fn        # 안 읽음은 바로 이동
    assert "function chipsHTML()" not in html


def test_tag_json_has_label_and_group(html):
    import re
    m = re.search(r"const TAGS = (\{.*?\});", html)
    assert m, "TAGS 상수가 없음"
    tags = json.loads(m.group(1))
    assert tags["ai"]["label"]
    assert tags["ai"]["group"]
    groups = {v["group"] for v in tags.values()}
    assert len(groups) == 3                     # AI / 개발 / 그 외


def test_card_tags_display_only(html):
    """카드 행 태그는 표시 전용 (remove-card-tag-filter-click).

    태그 클릭 = 필터 토글 동작을 제거 — 핸들러와 버튼 마크업이 없어야 하고,
    사이드바 태그 패널의 필터(data-ft)는 유지돼야 한다.
    """
    assert "querySelectorAll('.tg[data-tg]')" not in html   # 클릭 핸들러 제거
    assert "data-tg" not in html                            # 카드 태그에 클릭 대상 속성 없음
    assert '<span class="tg' in html                        # 버튼 → 표시 전용 span
    assert '<button class="tg' not in html
    assert "data-ft" in html                                # 사이드바 필터는 유지


def test_search_input_ime_composition_guard(html):
    """한글 IME 조합 보호 (fix-ime-composition-search).

    입력마다 render()가 input을 갈아끼우면 macOS 한글 IME 조합이 끊겨
    자모가 낱개(ㄱㅏㄴㅏ)로 입력된다. 조합 중에는 재렌더를 건너뛰고
    compositionend에서만 렌더하는 가드가 있어야 한다.
    """
    assert "isComposing" in html
    assert "compositionend" in html
