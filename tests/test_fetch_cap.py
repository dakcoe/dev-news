"""본문을 받을 때 크기 상한을 건다.

해커뉴스와 Lobsters는 PDF·데이터셋·릴리스 파일을 자주 링크한다. 상한이 없으면
그게 러너 메모리로 통째로 내려온 뒤 "HTML이 아니다"로 버려지고, 5xx면 그걸 세 번
반복한다. 거대한 HTML이면 파싱이 CPU를 수 분 먹어 회차가 25분 제한에 걸린다 —
그러면 커밋이 없어 사이트가 조용히 낡는다.

정상 기사는 중앙값 15KB, 최대 37KB다(실측 25건). 3MB 상한은 거기에 닿지 않는다.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from news.core import http  # noqa: E402


class FakeResp:
    def __init__(self, ctype="text/html", body=b"", length=None):
        self.status_code = 200
        self.headers = {"content-type": ctype}
        if length is not None:
            self.headers["content-length"] = str(length)
        self._body = body
        self.closed = False
        self.read = 0

    def iter_content(self, n):
        for i in range(0, len(self._body), n):
            self.read += n
            yield self._body[i:i + n]

    def close(self):
        self.closed = True

    @property
    def content(self):
        return getattr(self, "_content", b"")


def _patched(monkeypatch, resp):
    monkeypatch.setattr(http, "get", lambda url, **kw: resp)
    return resp


def test_상한까지만_읽는다(monkeypatch):
    resp = _patched(monkeypatch, FakeResp(body=b"x" * (5 * 1024 * 1024)))
    out = http.get_capped("https://e.com", max_bytes=1024 * 1024)
    assert len(out.content) <= 1024 * 1024 + 64 * 1024   # 청크 경계까지
    assert resp.closed


def test_HTML이_아니면_본문을_받지_않는다(monkeypatch):
    resp = _patched(monkeypatch, FakeResp(ctype="application/pdf", body=b"y" * 999))
    out = http.get_capped("https://e.com/big.pdf")
    assert out.content == b""
    assert resp.read == 0, "본문을 한 조각도 읽지 않아야 한다"


def test_큰_HTML은_버리지_않고_자른다(monkeypatch):
    """크기는 버릴 이유가 아니다. 통째로 버리면 긴 기사를 잃는다."""
    resp = _patched(monkeypatch, FakeResp(body=b"z" * (4 * 1024 * 1024),
                                          length=4 * 1024 * 1024))
    out = http.get_capped("https://e.com/long", max_bytes=1024 * 1024)
    assert len(out.content) > 0


def test_정상_크기_기사는_그대로_온다(monkeypatch):
    body = b"<html>" + b"a" * 20000 + b"</html>"
    _patched(monkeypatch, FakeResp(body=body, length=len(body)))
    assert http.get_capped("https://e.com").content == body


def test_본문_요청이_상한을_쓴다():
    """enrich가 http.get이 아니라 get_capped를 불러야 의미가 있다."""
    src = open(os.path.join(ROOT, "news", "core", "enrich.py"), encoding="utf-8").read()
    assert src.count("http.get_capped(") == 2, "본문과 README 둘 다 상한을 써야 한다"
    assert "http.get(" not in src.replace("http.get_capped(", "")
