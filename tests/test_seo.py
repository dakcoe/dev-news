"""검색 엔진과 AI 답변에 걸리기 위한 세팅.

이 파일이 지키는 것은 두 가지다. 검색 엔진이 페이지를 읽을 수 있는 상태인지
(제목·설명·canonical·구조화 데이터·사이트맵), 그리고 AI 크롤러가 막히지 않았는지
(robots.txt의 이름별 허용, llms.txt).

⚠️ 기사를 우리가 쓰지 않았으므로 NewsArticle로 표시하지 않는다. 그건 사실과 다르고
구글 구조화 데이터 정책의 '잘못된 표시'에 걸린다.
"""
import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from news.render import AI_AGENTS, render, site_url, write_seo_files  # noqa: E402


@pytest.fixture(scope="module")
def articles():
    with open(os.path.join(ROOT, "sample.json"), encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def html(tmp_path_factory, articles):
    out = tmp_path_factory.mktemp("seo") / "index.html"
    render(articles, str(out))
    return out.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def seo_dir(tmp_path_factory):
    from datetime import datetime
    d = tmp_path_factory.mktemp("seofiles")
    write_seo_files(str(d), datetime(2026, 9, 8))
    return d


# ---------------- 검색 결과에 뜨는 것 ----------------

def test_제목에_검색어가_들어간다(html):
    """'개발·AI 뉴스 · 날짜'만으로는 아무도 검색하지 않는다. 사람들이 실제로
    치는 말이 제목에 있어야 한다. 출처 이름은 설명에만 두고 제목에서는 뺐다 —
    제목이 길어지면 검색 결과에서 뒤가 잘린다."""
    title = re.search(r"<title>(.*?)</title>", html).group(1)
    for word in ("개발", "AI 뉴스", "한국어 요약"):
        assert word in title, f"제목에 '{word}'이(가) 없다: {title}"


def test_제목에_날짜가_없다(html):
    """날짜를 넣으면 검색 결과에 마지막 크롤링 날짜가 박제돼 오래된 페이지처럼
    보인다. 신선도는 sitemap의 lastmod와 dateModified가 알린다."""
    title = re.search(r"<title>(.*?)</title>", html).group(1)
    assert not re.search(r"\d{4}-\d{2}-\d{2}|\d{4}년|\d{1,2}월", title), title


def test_설명은_80자_이내다(html):
    """네이버 서치어드바이저가 80자 이내를 요구한다. 넘으면 뒤가 잘린다."""
    desc = re.search(r'<meta name="description" content="(.*?)">', html).group(1)
    assert 30 <= len(desc) <= 80, f"설명 길이 {len(desc)}자: {desc}"


def test_설명에_기사_제목이_들어가지_않는다(articles, html):
    """설명은 사이트를 설명해야 한다. 남의 기사 제목이 들어가면 이 사이트가
    무엇인지 알 수 없고, 매일 바뀌어 검색 엔진이 주제를 잡지 못한다."""
    desc = re.search(r'<meta name="description" content="(.*?)">', html).group(1)
    for a in articles:
        t = (a.get("title") or "").strip()
        if len(t) > 10:
            assert t not in desc, f"설명에 기사 제목이 들어갔다: {t}"


def test_오픈그래프_설명도_같은_문구다(html):
    desc = re.search(r'<meta name="description" content="(.*?)">', html).group(1)
    og = re.search(r'property="og:description" content="(.*?)"', html).group(1)
    tw = re.search(r'name="twitter:description" content="(.*?)"', html).group(1)
    assert og == desc == tw


def test_canonical이_한_개다(html):
    """같은 내용이 여러 주소로 잡히면 점수가 갈린다."""
    links = re.findall(r'<link rel="canonical" href="(.*?)"', html)
    assert links == [site_url() + "/"]


# ---------------- 공유했을 때 보이는 것 (오픈그래프) ----------------

@pytest.mark.parametrize("prop", [
    "og:type", "og:site_name", "og:locale", "og:url",
    "og:title", "og:description", "og:image",
    "og:image:width", "og:image:height", "og:image:alt",
])
def test_오픈그래프_항목이_있다(html, prop):
    assert f'property="{prop}"' in html


def test_트위터_카드는_큰_이미지다(html):
    assert '<meta name="twitter:card" content="summary_large_image">' in html
    assert 'name="twitter:image"' in html


def test_og_이미지가_절대주소다(html):
    """상대 주소를 쓰면 카카오톡·슬랙에서 그림이 안 뜬다."""
    src = re.search(r'property="og:image" content="(.*?)"', html).group(1)
    assert src.startswith("https://"), src


def test_og_이미지_파일이_실제로_있다():
    path = os.path.join(ROOT, "docs", "og.png")
    assert os.path.exists(path), "docs/og.png 없음 — 공유 미리보기가 빈칸이 된다"
    assert os.path.getsize(path) > 5000


# ---------------- 구조화 데이터 ----------------

def test_구조화_데이터가_유효한_JSON이다(html):
    raw = re.search(r'<script type="application/ld\+json">(.*?)</script>',
                    html, re.S).group(1)
    data = json.loads(raw)
    types = {n["@type"] for n in data["@graph"]}
    assert types == {"WebSite", "CollectionPage"}


def test_기사를_NewsArticle로_표시하지_않는다(html):
    """남의 기사다. 우리가 쓴 것처럼 표시하면 정책 위반이다."""
    assert "NewsArticle" not in html
    assert "BlogPosting" not in html


# ---------------- robots.txt ----------------

def test_robots가_사이트맵을_가리킨다(seo_dir):
    txt = (seo_dir / "robots.txt").read_text(encoding="utf-8")
    assert f"Sitemap: {site_url()}/sitemap.xml" in txt


def test_전체_허용이_맨_앞에_있다(seo_dir):
    txt = (seo_dir / "robots.txt").read_text(encoding="utf-8")
    assert txt.startswith("User-agent: *\nAllow: /\n")


@pytest.mark.parametrize("agent", AI_AGENTS)
def test_AI_크롤러가_이름으로_허용된다(seo_dir, agent):
    """Google-Extended, Applebot-Extended처럼 이름이 없으면 안 긁는 봇들이 있다.
    AI 답변의 출처로 인용되려면 이름을 적어 둬야 한다."""
    txt = (seo_dir / "robots.txt").read_text(encoding="utf-8")
    assert re.search(rf"^User-agent: {re.escape(agent)}\nAllow: /$", txt, re.M)


def test_아무것도_막지_않는다(seo_dir):
    txt = (seo_dir / "robots.txt").read_text(encoding="utf-8")
    assert "Disallow" not in txt


# ---------------- sitemap.xml ----------------

def test_사이트맵이_유효한_XML이고_주소가_맞다(seo_dir):
    import xml.etree.ElementTree as ET
    root = ET.parse(seo_dir / "sitemap.xml").getroot()
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    locs = [u.findtext(ns + "loc") for u in root.findall(ns + "url")]
    # 소개·개인정보 처리 페이지가 정적으로 있어야 크롤러와 광고 심사 봇이 찾는다
    assert locs[:4] == [site_url() + "/", site_url() + "/about/", site_url() + "/tour/", site_url() + "/privacy/"]
    # 학습 노트: 목록과 원고마다 한 줄 (learn/articles)
    from news import learn
    assert locs[4:] == [site_url() + "/learn/"] + [f'{site_url()}/learn/{a["slug"]}/' for a in learn.load()]
    assert (seo_dir / "learn" / "index.html").exists()


# ---------------- llms.txt ----------------

def test_llms가_사이트를_설명한다(seo_dir):
    """AI가 사이트를 요약할 때 읽는 안내문. 무엇을 모으고, 기사를 직접 쓰지는
    않는다는 점이 들어가야 한다."""
    txt = (seo_dir / "llms.txt").read_text(encoding="utf-8")
    assert txt.startswith("# dev-news")
    assert "직접 쓰지는 않는다" in txt
    assert site_url() in txt


# ---------------- 검색 도구 소유 확인 ----------------

def test_네이버_소유확인_태그가_남아있다(html):
    """네이버 서치어드바이저는 이 태그로 소유를 확인한다. 템플릿을 고치다
    지우면 등록이 풀리고 네이버 검색에서 사라진다."""
    assert ('<meta name="naver-site-verification" '
            'content="2f80c00d8aa3e1ce9eb9b7513b2fe24967f3e867">') in html


def test_favicon_ico가_루트에_있다():
    """크롤러 상당수는 <link rel="icon">을 안 읽고 /favicon.ico를 그냥 요청한다.
    없으면 검색 결과 아이콘이 기본 지구본으로 뜬다.

    ICO 컨테이너를 직접 읽는다 — 헤더 6바이트 뒤에 16바이트짜리 항목이 크기마다
    하나씩 온다. Pillow에 기대지 않으려고 struct로 푼다."""
    import struct
    path = os.path.join(ROOT, "docs", "favicon.ico")
    assert os.path.exists(path), "docs/favicon.ico 없음"
    raw = open(path, "rb").read()
    reserved, kind, count = struct.unpack("<HHH", raw[:6])
    assert (reserved, kind) == (0, 1), "ICO 헤더가 아니다"
    sizes = sorted(raw[6 + 16 * i] for i in range(count))
    assert sizes == [16, 32, 48], f"담긴 크기: {sizes}"


def test_head가_favicon_ico를_가리킨다(html):
    assert '<link rel="icon" href="/favicon.ico"' in html


def test_광고_크롤러가_robots에_이름으로_있다(seo_dir):
    """애드센스 크롤러는 `User-agent: *` 무리를 무시한다. 이름이 없으면 자기에게
    적용할 규칙이 없다고 본다.

    robots.txt가 아예 없던 2026-09-07에는 ads.txt가 확인됐는데, 08일에 이 파일을
    만들면서 광고 쪽 이름을 빠뜨리자 "ads.txt를 찾을 수 없음"으로 바뀌었다.
    """
    txt = (seo_dir / "robots.txt").read_text(encoding="utf-8")
    for agent in ("Mediapartners-Google", "AdsBot-Google", "AdsBot-Google-Mobile"):
        assert re.search(rf"^User-agent: {re.escape(agent)}\nAllow: /$", txt, re.M), agent


def test_ads_txt가_그대로_있다():
    """수익 연결이 걸린 파일이다. 지우거나 옮기면 광고가 끊긴다."""
    path = os.path.join(ROOT, "docs", "ads.txt")
    assert os.path.exists(path)
    body = open(path, encoding="utf-8").read().strip()
    assert body.startswith("google.com,"), body
    assert "DIRECT" in body


# ---------------- 봇이 읽는 것 ----------------

def test_프리렌더에_우리_문장이_보인다(tmp_path):
    """첫 화면 마크업에 남의 기사 제목·요약만 있으면 "요약만 모아둔 곳"으로
    읽힌다. 기사마다 쓴 '중요한 이유'가 스크립트 없이도 보여야 한다."""
    import re
    from news.render import render
    # why 는 최근 INLINE_DAYS 이내 기사에만 실린다(render.to_view_model). 날짜를
    # 고정해 두면 그 기간이 지나는 순간 기능과 무관하게 깨진다 — 2026-09-17에
    # 작성돼 사흘 뒤부터 실패하고 있었다.
    from datetime import datetime, timedelta
    from news.render import KST
    batch = (datetime.now(KST) - timedelta(hours=1)).isoformat()
    a = [{"title": "t", "url": "https://e.com/1", "source": "hackernews", "summary": "요약이다.",
          "why": "이유가 여기 있다.", "batch": batch, "batch_label": "오늘 08:00",
          "upvotes": 1, "comments": 1, "tags": []}]
    out = tmp_path / "index.html"
    render(a, str(out))
    markup = re.sub(r"<script\b.*?</script>", "", out.read_text(encoding="utf-8"), flags=re.S)
    assert "이유가 여기 있다." in markup
    assert 'class="foot"' in markup and 'href="/about/"' in markup and 'href="/privacy/"' in markup
    assert "회차당 최대 20건을 고릅니다" in markup


def test_정적_소개_페이지가_같은_글을_담는다(tmp_path):
    """앱 안의 소개 화면은 스크립트가 그려서 봇에게는 빈 화면이다. /about/ 와
    /privacy/ 를 정적으로 내보내고, 글은 about_copy() 한 곳에서 온다."""
    from news.render import write_static_pages, about_copy
    about = {"github": "https://github.com/x/y", "author": "me", "author_url": "https://github.com/x",
             "bio": "안녕", "coffee": "https://pay.example/z", "coffee_label": "커피"}
    write_static_pages(str(tmp_path), about, None)
    a = (tmp_path / "about" / "index.html").read_text(encoding="utf-8")
    p = (tmp_path / "privacy" / "index.html").read_text(encoding="utf-8")
    for sec in about_copy(None):
        assert sec["title"] in a
    assert "https://github.com/x.png?size=208" in a and "커피" in a and "/issues" in a
    # 본문이 실렸는지만 본다. 예전에는 localStorage 라는 단어를 찾았는데,
    # 그 말을 빼는 것이 개인정보 문단을 다시 쓴 이유였다.
    assert "개인정보 처리" in p and "수집되는 정보" in p and "커피" not in p
    assert 'rel="canonical" href="' in a


def test_첫_버튼은_홈페이지로_사진은_깃허브에서(tmp_path):
    """github.io 페이지를 열되, 프로필 사진은 여전히 github.com/<아이디>.png 다."""
    from news.render import write_static_pages
    write_static_pages(str(tmp_path), {"author_url": "https://github.com/x", "homepage": "https://x.github.io"}, None)
    a = (tmp_path / "about" / "index.html").read_text(encoding="utf-8")
    assert 'href="https://x.github.io"' in a and "https://github.com/x.png?size=208" in a
    assert 'href="https://github.com/x"' not in a


def test_후원_주소는_정적_페이지에서도_검사한다(tmp_path):
    from news.render import write_static_pages
    write_static_pages(str(tmp_path), {"coffee": "javascript:alert(1)", "github": "https://github.com/x/y"}, None)
    a = (tmp_path / "about" / "index.html").read_text(encoding="utf-8")
    assert "javascript:" not in a
