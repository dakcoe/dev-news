"""수집용 공용 HTTP 클라이언트 (consolidate-http).

요청이 12개 파일 17군데에서 제각각 나갔고 User-Agent만 10종이었다. 흩어진 것
자체보다 함께 빠져 있던 것들이 문제였다 — 재시도가 없어 피드 하나가 순간
502만 떠도 그 블로그는 그날 통째로 빠졌다.

requests를 감싸기만 하고 의미는 바꾸지 않는다. 응답을 그대로 돌려주므로
호출부는 status_code·text·content를 하던 대로 쓴다.
"""
from __future__ import annotations

import ipaddress
import socket
import time
from urllib.parse import urljoin, urlparse

import requests

# 정직하게 밝힌다. 브라우저 위장은 쓰지 않는다 — 상대가 막을 근거를 주는 편이
# 낫고, 차단당하면 fetch_health에 blocked로 남아 진단이 된다.
USER_AGENT = "dev-news/1.0 (+https://github.com/dakcoe/dev-news)"

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    # Accept가 없으면 일부 서버(Cloudflare 뒤)가 봇으로 보고 403을 준다
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}

MAX_ATTEMPTS = 3        # 최초 1회 + 재시도 2회
BACKOFF_BASE = 1.0      # 1s → 2s

# 다시 걸어 볼 값어치가 있는 응답. 4xx는 같은 답이 오고, 429는 상대가 쉬라는
# 뜻이라 회차 안에서 조르지 않는다.
RETRY_CODES = range(500, 600)


MAX_BYTES = 3 * 1024 * 1024      # 본문 상한. 정상 기사는 중앙값 15KB·최대 37KB다.


# 수집하는 주소는 남이 정한다 — 해커뉴스나 dev.to 에 글을 올리는 사람이 링크를
# 고른다. 그 주소가 사설망을 가리키면 수집기가 대신 집 안의 서비스를 긁어
# 본문을 공개 페이지에 싣는다. 이 기계는 Tailscale(100.64.0.0/10) 위에서
# 다른 서비스도 돌린다.
MAX_REDIRECTS = 5
_CGNAT = ipaddress.ip_network("100.64.0.0/10")   # ipaddress 는 이 대역을 사설로 안 본다


def _blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_reserved or ip.is_multicast or ip.is_unspecified
            or (ip.version == 4 and ip in _CGNAT))


def check_public(url: str) -> None:
    """공인 주소를 가리키는 http(s) 주소가 아니면 거른다.

    ponytail: 이름을 풀고 나서 requests 가 다시 풀기 때문에 DNS 리바인딩은 못 막는다.
    그건 소켓을 직접 열어야 막힌다 — 게시되는 본문을 지키는 데는 이걸로 충분하다.
    """
    parts = urlparse(url)
    if parts.scheme not in ("http", "https"):
        raise requests.RequestException(f"허용하지 않는 스킴: {url}")
    host = parts.hostname
    if not host:
        raise requests.RequestException(f"호스트가 없다: {url}")
    try:
        infos = socket.getaddrinfo(host, parts.port or (443 if parts.scheme == "https" else 80),
                                   proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise requests.RequestException(f"이름을 풀지 못했다: {host}") from e
    for info in infos:
        if _blocked(ipaddress.ip_address(info[4][0])):
            raise requests.RequestException(f"사설망 주소라 받지 않는다: {host}")


def get(url: str, **kwargs) -> requests.Response:
    """GET 요청. 5xx와 연결 오류에만 재시도한다.

    호출부가 headers를 주면 그 값이 이긴다 — 기본값 위에 덮어쓴다.

    리다이렉트는 requests 에 맡기지 않고 직접 따라간다. 맡기면 첫 주소만 검사해도
    상대가 302로 사설망에 보낼 수 있다. 한 번 뛸 때마다 다시 검사한다.
    """
    follow = kwargs.pop("allow_redirects", True)
    history: list[requests.Response] = []
    for _ in range(MAX_REDIRECTS + 1):
        resp = _get_once(url, **kwargs)
        if not (follow and resp.is_redirect and resp.headers.get("location")):
            resp.history = history
            return resp
        resp.close()
        history.append(resp)
        url = urljoin(url, resp.headers["location"])
    raise requests.TooManyRedirects(f"리다이렉트가 {MAX_REDIRECTS}번을 넘었다: {url}")


def _get_once(url: str, **kwargs) -> requests.Response:
    check_public(url)
    headers = {**DEFAULT_HEADERS, **(kwargs.pop("headers", None) or {})}
    kwargs.setdefault("timeout", 15)
    kwargs["allow_redirects"] = False

    last_error: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            resp = requests.get(url, headers=headers, **kwargs)
        except requests.RequestException as e:
            last_error = e
        else:
            if resp.status_code not in RETRY_CODES:
                return resp
            last_error = None
            if attempt == MAX_ATTEMPTS - 1:
                return resp

        if attempt < MAX_ATTEMPTS - 1:
            time.sleep(BACKOFF_BASE * (2 ** attempt))

    raise last_error if last_error else requests.RequestException(url)


def get_capped(url: str, max_bytes: int = MAX_BYTES,
               allow_types: tuple[str, ...] = ("html", "xml"),
               **kwargs) -> requests.Response:
    """헤더를 먼저 받고, 본문은 상한까지만 읽는다.

    get()은 본문을 통째로 받은 뒤에야 호출부가 content-type을 본다. 해커뉴스와
    Lobsters는 PDF·데이터셋·릴리스 파일을 자주 링크하는데, 그게 러너 메모리로
    다 내려온 뒤 "HTML이 아니다"로 버려진다. 5xx면 그걸 세 번 반복한다.
    거대한 HTML이면 파싱이 CPU를 수 분 먹어 회차가 25분 제한에 걸린다.

    상한에 걸리면 거기까지만 돌려준다 — 본문 추출은 앞부분만으로도 대개 된다.
    """
    kwargs["stream"] = True
    resp = get(url, **kwargs)
    # 형식이 아니면 본문을 아예 받지 않는다. 크기는 이유가 되지 않는다 —
    # 큰 HTML은 잘라서 받으면 되고, 통째로 버리면 긴 기사를 잃는다.
    ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
    if ctype and not any(t in ctype for t in allow_types):
        resp.close()
        resp._content = b""
        resp._content_consumed = True
        return resp

    chunks, total = [], 0
    for chunk in resp.iter_content(64 * 1024):
        chunks.append(chunk)
        total += len(chunk)
        if total >= max_bytes:
            break
    resp.close()
    resp._content = b"".join(chunks)
    resp._content_consumed = True
    return resp
