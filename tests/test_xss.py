"""외부에서 온 값이 마크업으로 실행되지 않는지.

기사 제목·요약·썸네일 주소·기사 주소는 전부 남이 정하는 값이다. 해커뉴스나
Lobsters에 글을 올리는 사람이 그 값을 쓴다. 2026-09-15 리뷰에서 네 경로가 전부
재현됐다.

  1. 제목의 "</script>" 로 스크립트를 끊고 그 뒤를 마크업으로 만들기
  2. 요약문에 넣은 태그가 상세 패널에서 실행
  3. 썸네일 주소가 src 속성을 깨고 나오기
  4. "javascript:" 주소가 링크에 실려 클릭 한 번에 실행

원칙은 하나다. **마크업을 만드는 곳을 좁히고 거기서만 이스케이프한다.** 삽입
지점마다 처리를 덧붙이면 다음에 행을 하나 더 그릴 때 또 뚫린다. 그래서 이 파일은
결과 HTML만이 아니라 템플릿이 실제로 헬퍼를 거치는지도 함께 본다.
"""
import os
import re
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from news.render import _json_for_script, _safe_url, render  # noqa: E402

PAYLOAD = "window.__pwned=1"

POISON = [{
    "title": f'boom </script><img src=x onerror="{PAYLOAD}">',
    "ko_title": f'boom </script><img src=x onerror="{PAYLOAD}">',
    "url": "javascript:" + PAYLOAD,
    "source": "hackernews",
    "from": "Hacker News",
    "summary": f'요약 앞. <img src=x onerror="{PAYLOAD}"> 뒤.',
    "why": f'왜중요 <img src=x onerror="{PAYLOAD}">',
    "image": f'x" onerror="{PAYLOAD}" x="',
    "batch": "2026-09-15T00:00:00+09:00",
    "batch_label": "9월 15일 00:00",
    "upvotes": 1, "comments": 1, "tags": [],
}]


@pytest.fixture(scope="module")
def html():
    out = os.path.join(tempfile.mkdtemp(), "index.html")
    render(list(POISON), out)
    return open(out, encoding="utf-8").read()


@pytest.fixture(scope="module")
def markup(html):
    """스크립트 블록을 걷어낸 '진짜 마크업'. 기사 데이터는 JS 문자열 안에
    남아 있어도 되지만, 마크업으로 새어 나오면 안 된다."""
    return re.sub(r"<script\b.*?</script>", "", html, flags=re.S | re.I)


@pytest.fixture(scope="module")
def template():
    with open(os.path.join(ROOT, "news", "template.html"), encoding="utf-8") as f:
        return f.read()


# ---------------- 결과 HTML ----------------

def test_스크립트가_기사_제목으로_끊기지_않는다(html):
    """제목에 "</script>"가 있으면 브라우저가 거기서 스크립트를 끝낸다.
    여는 태그와 닫는 태그 수가 같아야 한다."""
    assert len(re.findall(r"<script\b", html, re.I)) == \
           len(re.findall(r"</script\s*>", html, re.I))
    assert "<\\/script>" in html, "JSON에서 </ 를 탈출하지 않았다"


def test_마크업에_실행_가능한_조각이_없다(markup):
    for bad in ("onerror=\"window", "onerror='window", "javascript:", "<img src=x"):
        assert bad not in markup, f"마크업에 {bad!r} 가 살아 있다"


def test_제목과_요약은_글자로만_보인다(markup):
    """지워버리면 안 된다. 이스케이프해서 그대로 보여야 한다."""
    assert "&lt;img src=x" in markup
    assert "boom &lt;/script&gt;" in markup


def test_javascript_주소는_링크에서_죽는다(markup):
    hrefs = re.findall(r'<a[^>]+href="([^"]*)"', markup)
    assert hrefs, "정적 프리렌더에 링크가 없다"
    for h in hrefs:
        assert not h.lower().startswith("javascript:"), h


# ---------------- 헬퍼 ----------------

@pytest.mark.parametrize("bad", [
    "javascript:alert(1)", "JavaScript:alert(1)", "  javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>", "vbscript:msgbox", "//evil.com",
])
def test_안전하지_않은_주소는_빈_값이_된다(bad):
    assert _safe_url(bad) == ""


@pytest.mark.parametrize("ok", [
    "https://example.com/a?b=1", "http://example.com/", "HTTPS://EXAMPLE.COM/",
])
def test_정상_주소는_통과한다(ok):
    assert _safe_url(ok) == ok


def test_JSON_헬퍼가_태그_조각을_탈출한다():
    got = _json_for_script({"t": "</script><!--", "u": "a b"})
    for raw in ("</script>", "<!--", " "):
        assert raw not in got, raw


def test_JSON_헬퍼가_값을_바꾸지_않는다():
    """이스케이프해도 JSON으로서는 같은 값이어야 한다."""
    import json
    data = {"t": "</script>", "u": "a b", "k": "정상 한국어"}
    assert json.loads(_json_for_script(data)) == data


# ---------------- 템플릿 구조 ----------------

def test_서버가_본문_HTML을_조립하지_않는다():
    """상세 본문을 "<p>요약</p>" 문자열로 보내면 이스케이프할 자리가 사라진다.
    문단 목록만 넘기고 <p>는 템플릿이 만든다."""
    with open(os.path.join(ROOT, "news", "render.py"), encoding="utf-8") as f:
        src = f.read()
    assert '"<p>{p}</p>"' not in src and "'<p>{p}</p>'" not in src
    assert '"paras"' in src


def test_기사_주소를_인라인_코드에_싣지_않는다(template):
    """onclick 안 JS 문자열에 주소를 넣으면 작은따옴표 하나로 뚫린다.
    escA는 따옴표를 막지 않으므로 이스케이프로는 못 고친다."""
    assert "markRead(\\''+d.url" not in template
    assert "window.open(\\''+d.url" not in template
    assert "data-ext=" in template


@pytest.mark.parametrize("expr", [
    "escA(d.title)", "escA(d.snip)", "escA(d.why)", "escA(e.t)",
    "safeU(d.img)", "safeU(d.url)",
])
def test_삽입부가_헬퍼를_거친다(template, expr):
    assert expr in template, f"{expr} 가 템플릿에 없다"


def test_safeU가_정의돼_있다(template):
    assert "const safeU=" in template
    assert "https?:" in template
