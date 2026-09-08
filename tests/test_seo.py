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


def test_설명은_비어있지_않고_길이가_적당하다(html):
    desc = re.search(r'<meta name="description" content="(.*?)">', html).group(1)
    assert 50 <= len(desc) <= 200, f"설명 길이 {len(desc)}자: {desc}"


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
    assert locs == [site_url() + "/"]


# ---------------- llms.txt ----------------

def test_llms가_사이트를_설명한다(seo_dir):
    """AI가 사이트를 요약할 때 읽는 안내문. 무엇을 모으고, 기사를 직접 쓰지는
    않는다는 점이 들어가야 한다."""
    txt = (seo_dir / "llms.txt").read_text(encoding="utf-8")
    assert txt.startswith("# dev-news")
    assert "직접 쓰지는 않는다" in txt
    assert site_url() in txt
