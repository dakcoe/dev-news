"""수집 주소가 사설망을 가리키면 받지 않는다.

기사 주소는 남이 정한다. 해커뉴스나 dev.to 에 글을 올리는 사람이 링크를 고르므로
`http://127.0.0.1:8080/` 나 Tailscale 주소를 올리면 수집기가 대신 집 안의 서비스를
긁고, 그 본문이 요약을 거쳐 공개 페이지에 실린다. 2026-09-19 리뷰에서 나왔다.
"""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
import requests

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from news.core import http  # noqa: E402


def _resolves_to(ip):
    """getaddrinfo 를 대신한다 — 테스트가 진짜 DNS 를 타면 안 된다."""
    return lambda host, port, **kw: [(2, 1, 6, "", (ip, port or 80))]


@pytest.mark.parametrize("ip", [
    "127.0.0.1",        # 루프백
    "10.0.0.5",         # 사설
    "192.168.0.10",
    "172.16.0.1",
    "169.254.169.254",  # 클라우드 메타데이터
    "100.101.102.103",  # Tailscale (CGNAT) — ipaddress 는 이걸 사설로 안 본다
    "0.0.0.0",
])
def test_사설망_주소는_받지_않는다(ip):
    with patch("news.core.http.socket.getaddrinfo", _resolves_to(ip)):
        with pytest.raises(requests.RequestException):
            http.check_public("http://any.example/x")


def test_공인_주소는_통과한다():
    with patch("news.core.http.socket.getaddrinfo", _resolves_to("93.184.216.34")):
        http.check_public("https://example.com/x")


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "gopher://x/1", "ftp://x/y", "javascript:alert(1)",
])
def test_http가_아니면_받지_않는다(url):
    with pytest.raises(requests.RequestException):
        http.check_public(url)


def test_리다이렉트도_한_번씩_검사한다():
    """첫 주소만 보면 상대가 302 로 사설망에 보낼 수 있다. requests 에 맡기지
    않고 직접 따라가며 매 번 검사하는 이유다."""
    hop = MagicMock(status_code=302, is_redirect=True,
                    headers={"location": "http://internal.example/secret"})
    def fake_resolve(host, port, **kw):
        return [(2, 1, 6, "", ("127.0.0.1" if host == "internal.example"
                               else "93.184.216.34", port or 80))]
    with patch("news.core.http.socket.getaddrinfo", fake_resolve), \
         patch("news.core.http.requests.get", return_value=hop):
        with pytest.raises(requests.RequestException, match="사설망"):
            http.get("https://evil.example/start")


def test_리다이렉트가_끝없이_돌면_멈춘다():
    hop = MagicMock(status_code=302, is_redirect=True,
                    headers={"location": "https://example.com/next"})
    with patch("news.core.http.socket.getaddrinfo", _resolves_to("93.184.216.34")), \
         patch("news.core.http.requests.get", return_value=hop):
        with pytest.raises(requests.TooManyRedirects):
            http.get("https://example.com/start")
