"""레일 하단 GitHub 저장소 링크 (github-link-button)."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(ROOT, "news", "template.html"), encoding="utf-8") as f:
    TEMPLATE = f.read()


def test_repo_link_exists():
    assert 'href="https://github.com/dakcoe/dev-news"' in TEMPLATE


def test_link_opens_new_tab_safely():
    m = re.search(r'<a[^>]*href="https://github\.com/dakcoe/dev-news"[^>]*>', TEMPLATE)
    assert m, "저장소 링크 앵커가 없다"
    tag = m.group(0)
    assert 'target="_blank"' in tag
    assert 'rel="noopener' in tag


def test_link_is_inside_rail_without_data_v():
    rail = re.search(r'<nav class="rail">(.*?)</nav>', TEMPLATE, re.S)
    assert rail, "레일 마크업이 없다"
    m = re.search(r'<a[^>]*github\.com/dakcoe/dev-news[^>]*>', rail.group(1))
    assert m, "링크가 레일 안에 없다"
    # data-v가 붙으면 뷰 전환 핸들러가 링크를 탭으로 오인한다
    assert "data-v" not in m.group(0)
