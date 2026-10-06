"""학습 노트: 날짜가 오지 않은 원고는 페이지·목록·사이트맵 어디에도 나오지 않는다."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from news import learn  # noqa: E402


def _write(d, slug, order, date):
    meta = ('{"slug": "%s", "cat": "확률변수론", "order": %d, "title": "t%s", '
            '"desc": "d", "lead": "l", "date": "%s"}' % (slug, order, slug, date))
    (d / f"{slug}.html").write_text(f"<!--META {meta} -->\n<h2 id=\"s1\">1. 절</h2><p>본문</p>\n",
                                    encoding="utf-8")


def test_오늘_이후_날짜의_원고는_내보내지_않는다(tmp_path):
    src = tmp_path / "src"; src.mkdir()
    _write(src, "p-1", 1, "2026-10-07")
    _write(src, "p-2", 2, "2026-10-09")
    docs = tmp_path / "docs"
    paths = learn.build(str(docs), "https://x", str(src), today="2026-10-08")
    assert paths == ["/learn/", "/learn/p-1/"]
    assert not (docs / "learn" / "p-2").exists()
    assert "p-2" not in (docs / "learn" / "index.html").read_text(encoding="utf-8")
    # 다음 글 링크도 아직 안 나온 글을 가리키지 않는다
    assert "/learn/p-2/" not in (docs / "learn" / "p-1" / "index.html").read_text(encoding="utf-8")
    # 날짜 당일에는 나온다
    assert learn.build(str(docs), "https://x", str(src), today="2026-10-09")[-1] == "/learn/p-2/"


def test_글_번호는_나온_글_순서로_매긴다(tmp_path):
    src = tmp_path / "src"; src.mkdir()
    _write(src, "a", 0, "2026-10-01")
    _write(src, "b", 5, "2026-10-01")
    docs = tmp_path / "docs"
    learn.build(str(docs), "https://x", str(src), today="2026-10-01")
    assert "확률변수론 1편" in (docs / "learn" / "a" / "index.html").read_text(encoding="utf-8")
    assert "확률변수론 2편" in (docs / "learn" / "b" / "index.html").read_text(encoding="utf-8")


def test_학습_노트에도_애드센스_코드가_있다(tmp_path):
    src = tmp_path / "src"; src.mkdir()
    _write(src, "a", 1, "2026-10-01")
    docs = tmp_path / "docs"
    learn.build(str(docs), "https://x", str(src), today="2026-10-01")
    for p in [docs / "learn" / "index.html", docs / "learn" / "a" / "index.html"]:
        assert "ca-pub-9719970909376058" in p.read_text(encoding="utf-8")
