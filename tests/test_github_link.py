"""레일 맨 아래 GitHub 아이콘은 소개 화면을 연다 (github-link-button → about-view).

저장소로 바로 튀는 대신 소개 화면에서 저장소·문의·후원 링크를 함께 보여 준다.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(ROOT, "news", "template.html"), encoding="utf-8") as f:
    TEMPLATE = f.read()


def test_레일_아이콘은_소개_뷰_버튼이다():
    rail = re.search(r'<nav class="rail">(.*?)</nav>', TEMPLATE, re.S)
    assert rail, "레일 마크업이 없다"
    assert 'data-v="about"' in rail.group(1)
    assert "github.com/dakcoe" not in rail.group(1), "레일에서 바로 저장소로 나가면 안 된다"


def test_소개_뷰에_저장소_링크가_새_탭으로_있다():
    body = TEMPLATE[TEMPLATE.index("function aboutHTML("):]
    m = re.search(r'<a class="go" href="\'\+repo\+\'"[^>]*>', body)
    assert m, "저장소 링크가 없다"
    assert 'target="_blank"' in m.group(0) and 'rel="noopener' in m.group(0)


def test_후원_버튼은_주소가_있을_때만():
    body = TEMPLATE[TEMPLATE.index("function aboutHTML("):]
    assert "(coffee?" in body
    assert "safeU(a.coffee)" in body, "후원 주소도 남이 정하는 값처럼 다룬다"


def test_소개_설정이_페이지에_실린다():
    assert "const ABOUT = __ABOUT_JSON__;" in TEMPLATE
    r = open(os.path.join(ROOT, "news", "render.py"), encoding="utf-8").read()
    assert '"__ABOUT_JSON__"' in r
    import yaml
    cfg = yaml.safe_load(open(os.path.join(ROOT, "config.yaml"), encoding="utf-8"))
    assert cfg["about"]["github"].startswith("https://github.com/")
