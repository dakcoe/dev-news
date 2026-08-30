"""수집용 공용 HTTP 클라이언트 (consolidate-http).

요청이 12개 파일 17군데에서 제각각 나갔고 User-Agent만 10종이었다. 흩어진 것
자체보다 함께 빠져 있던 것들이 문제였다 — 재시도가 없어 피드 하나가 순간
502만 떠도 그 블로그는 그날 통째로 빠졌다.

requests를 감싸기만 하고 의미는 바꾸지 않는다. 응답을 그대로 돌려주므로
호출부는 status_code·text·content를 하던 대로 쓴다.
"""
from __future__ import annotations

import time

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


def get(url: str, **kwargs) -> requests.Response:
    """GET 요청. 5xx와 연결 오류에만 재시도한다.

    호출부가 headers를 주면 그 값이 이긴다 — 기본값 위에 덮어쓴다.
    """
    headers = {**DEFAULT_HEADERS, **(kwargs.pop("headers", None) or {})}
    kwargs.setdefault("timeout", 15)

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
