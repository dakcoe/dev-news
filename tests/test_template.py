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


def test_update_schedule_text_matches_cron(html):
    """안내 문구가 실제 Actions 스케줄과 일치해야 한다 (fix-update-schedule-text).

    워크플로는 cron "0 7,15,23 * * *"(UTC) = KST 00·08·16시 하루 3회인데
    페이지에는 "매일 오전 9시"로 적혀 있었다.

    지금은 정각을 피해 :55에 돈다(깃허브 예약 작업이 정각일수록 밀린다).
    분을 반올림해서 비교한다 — 15:55은 화면의 "16시"와 같은 회차다.
    """
    import re
    assert "9시" not in html
    # 소스 뷰 + 뉴스 뷰 서브텍스트 + 스크립트 실행 전 목록(add-seo-prerender)
    assert html.count("매일 00시·08시·16시") == 3

    wf = os.path.join(ROOT, ".github", "workflows")
    crons = []
    for name in os.listdir(wf):
        with open(os.path.join(wf, name), encoding="utf-8") as f:
            crons += re.findall(r'cron:\s*"([^"]+)"', f.read())
    assert crons, "워크플로에 cron이 없음"
    kst = set()
    for c in crons:
        minute, hours = c.split()[0], c.split()[1]
        for h in hours.split(","):
            # UTC → KST(+9), 분을 시 단위로 반올림
            total = (int(h) + 9) * 60 + int(minute)
            kst.add(round(total / 60) % 24)
    assert sorted(kst) == [0, 8, 16], f"cron {crons} → KST {sorted(kst)}"


def test_mobile_layout_not_squeezed(html):
    """모바일 카드 본문 붕괴 재현 테스트 (fix-mobile-layout).

    ≤820px에서 .acts가 그리드 옆 칸에 남아 있으면 본문(.mid)이 98px까지 줄어
    제목이 한 단어씩 세로로 떨어진다. .acts는 카드 하단 전체 폭 행으로 내려가고
    좌측 레일은 하단 내비로 전환돼야 한다.
    """
    mobile = html.split("@media (max-width:820px)")[1].split("}\n")[0:20]
    mobile = "@media (max-width:820px)" + "}\n".join(mobile)
    # 본문 옆에 acts 칸이 없다 — 2칸 그리드(체크박스 + 본문)
    assert ".row{grid-template-columns:auto minmax(0,1fr);" in mobile
    assert "auto minmax(0,1fr) auto" not in mobile
    # acts는 하단 전체 폭 행
    assert "grid-column:1/-1" in mobile
    # 레일은 하단 고정 내비 — 스크롤 영역이 그만큼 하단 여백을 확보
    assert "bottom:0;top:auto" in mobile
    assert "flex-direction:row" in mobile
    assert "88px" in mobile, "하단 내비 높이만큼 스크롤 여백이 없음"
    # 전체 스케일 축소 — fixed 요소 좌표가 틀어지지 않게 .inner에만 건다
    assert ".inner{zoom:.8}" in mobile
    assert "body{zoom" not in mobile


def test_search_partial_render_keeps_input(html):
    """한글 IME 조합 보호 v2 (fix-search-partial-render).

    v1(조합 끝날 때만 렌더)은 맥 IME가 단어 커밋까지 조합을 유지해 검색이
    지연되는 부작용이 있었다. 검색 입력은 목록(.layout)만 부분 갱신해
    input이 교체되지 않아야 한다 — 조합 유지 + 조합 중 실시간 검색.
    """
    assert "function layoutHTML" in html
    assert "function renderList" in html
    assert "renderList()" in html
    # oninput이 전체 render()로 input을 갈아끼우던 이전 방식이 아니어야 한다
    assert "q=e.target.value; render()" not in html


def test_인트로_커서가_글자_경계에_선다(html):
    """덮개는 글자보다 4px 넓다(오른쪽 끝을 확실히 덮으려고 둔 여유). 이동량을
    덮개 폭(100%) 기준으로 잡으면 한 걸음이 24.4px가 되는데 글자 한 칸은 24px다.
    걸음마다 0.4px씩 밀려 커서가 글자 안으로 파고들고, 여덟 걸음째에 글자가 다
    드러난 뒤 두 걸음을 빈자리에서 혼자 미끄러진다.

    윈도우 실측: 고치기 전 0·24.4·48.8…244, 고친 뒤 0·24·48…240.
    """
    import re
    kf = re.search(r"@keyframes introReveal\{([^}]*\}?[^}]*)\}", html).group(1)
    assert "translateX(calc(100% - 4px))" in kf, kf
    # translateX(100%)는 상세 패널이 화면 밖에 대기하는 데도 쓴다 — 거긴 정상이다.
    assert "translateX(100%)" not in kf


def test_인트로가_앱_스크립트보다_먼저_켜진다(html):
    """앱 스크립트는 1.4MB JSON을 파싱하느라 메인 스레드를 600ms 막는다.
    거기서 인트로를 켜면 덮개가 컴포지터에 있어도 시작이 밀려, 글자가 덮인 채
    멈춰 있다가 한꺼번에 나타난다."""
    intro = html.index('<div class="intro"')
    start = html.index("classList.add('ready')")
    app = html.rindex("PAGE = ")          # 큰 앱 스크립트의 앞부분
    assert intro < start < app, "인트로 시작이 앱 스크립트 뒤에 있다"


def test_색인_실패가_무한_재시도로_돌지_않는다(html):
    """실패 직후 null로 되돌리면 renderList가 곧바로 ensureIndex를 다시 부르고
    그게 또 실패해 끝없이 요청이 나간다."""
    assert "INDEX='fail'; renderList();" in html
    # 풀어 주는 곳은 검색어가 바뀌는 자리 하나뿐이어야 한다
    assert html.count("if(INDEX==='fail') INDEX=null;") == 1


def test_색인에_태그가_없는_기사를_태그로_지우지_않는다(html):
    """색인의 5%는 태그가 비어 있다. 없는 값으로 거르면 태그를 한 번 고른
    사람은 그 기사들을 영영 검색으로 못 찾는다."""
    assert "tagSel.size && (e.g||[]).length &&" in html


def test_선택된_출처는_0건이어도_목록에_남는다(html):
    """버튼이 사라지면 무엇이 걸려 있는지 보이지도 않고 풀 수도 없다."""
    assert "filter(k=>sc[k] || k===filter)" in html


def test_겹침이_열리면_방문_기록을_한_칸_쌓는다(html):
    """모바일에서 한 손으로 볼 때 가장 자연스러운 동작이 뒤로가기다. 그런데
    기사를 열고 뒤로가기를 누르면 겹침만 닫히는 게 아니라 사이트를 나갔다."""
    assert "pushState({devnewsOverlay:1}" in html
    assert "addEventListener('popstate'" in html


def test_칸은_한_번만_쌓는다(html):
    """기사를 여러 개 열어도 기록이 그만큼 쌓이면, 사이트를 나가려고 뒤로가기를
    여러 번 눌러야 한다."""
    assert "if(overlayDepth) return;" in html


def test_X로_닫아도_쌓인_칸을_되돌린다(html):
    """닫는 길이 둘(뒤로가기·X)인데 한쪽만 기록을 정리하면 어긋난다."""
    for fn in ("function closeDetail()", "facetOpen=false; render(); popOverlay()"):
        assert fn in html


def test_공유_메뉴는_숨김_속성을_지킨다(html):
    """`.sharemenu`에 display를 지정하면 hidden 속성(브라우저 기본값
    display:none)을 이겨서, 메뉴가 처음부터 펼쳐진 채로 보인다."""
    assert ".sharemenu[hidden]{display:none}" in html


def test_공유_주소는_기사_번호가_아니라_원문_주소를_담는다(html):
    """번호는 회차마다 바뀐다. 어제 공유한 링크가 오늘 다른 기사를 연다."""
    assert "'#a=' + encodeURIComponent(u)" in html
    assert "openFromHash();" in html


def test_공유_주소에_달을_같이_담는다(html):
    """30일이 지난 기사는 월별 샤드에서 찾아야 열린다."""
    assert "d.month || (d.batch || '').slice(0, 7)" in html
    assert "if(m){ openArchived(url, m); return true; }" in html


def test_뉴스카드에_남의_도메인_그림을_얹지_않는다(html):
    """썸네일을 캔버스에 그리면 그 캔버스를 읽을 수 없게 되어(tainted)
    복사가 통째로 실패한다. 카드는 글자만 그린다."""
    card = html[html.index("function drawCard("):html.index("function shareText(")]
    assert "drawImage" not in card


def test_클립보드_이미지는_약속을_그대로_넘긴다(html):
    """toBlob 콜백까지 기다리면 Safari가 클릭과 무관한 쓰기로 보고 거절한다."""
    assert "new ClipboardItem({'image/png':blob})" in html
