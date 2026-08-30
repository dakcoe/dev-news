"""공용 HTTP 클라이언트 (consolidate-http).

동기: 요청이 12개 파일 17군데에서 제각각 나갔고 UA만 10종이었다. 흩어진 것보다
함께 빠져 있던 것들이 문제였다 — 재시도가 없어 피드 하나가 순간 502만 떠도 그
블로그는 그날 통째로 빠졌다.
"""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
import requests

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from news.core import http  # noqa: E402


def _resp(code=200):
    r = MagicMock()
    r.status_code = code
    return r


# ------------------------------------------------------------------ 기본 헤더
def test_default_user_agent_is_attached():
    with patch("news.core.http.requests.get", return_value=_resp()) as g:
        http.get("https://e.com/x")
    headers = g.call_args.kwargs["headers"]
    assert "dev-news" in headers["User-Agent"]
    assert headers["Accept"]


def test_caller_headers_win():
    with patch("news.core.http.requests.get", return_value=_resp()) as g:
        http.get("https://e.com/x", headers={"User-Agent": "custom/1.0"})
    assert g.call_args.kwargs["headers"]["User-Agent"] == "custom/1.0"


def test_params_and_timeout_pass_through():
    with patch("news.core.http.requests.get", return_value=_resp()) as g:
        http.get("https://e.com/x", params={"a": 1}, timeout=7)
    assert g.call_args.kwargs["params"] == {"a": 1}
    assert g.call_args.kwargs["timeout"] == 7


# ------------------------------------------------------------------ 재시도
def test_retries_on_5xx():
    with patch("news.core.http.requests.get",
               side_effect=[_resp(503), _resp(502), _resp(200)]) as g, \
         patch("news.core.http.time.sleep"):
        assert http.get("https://e.com/x").status_code == 200
    assert g.call_count == 3


def test_retries_on_connection_error():
    with patch("news.core.http.requests.get",
               side_effect=[requests.ConnectionError("boom"), _resp(200)]) as g, \
         patch("news.core.http.time.sleep"):
        assert http.get("https://e.com/x").status_code == 200
    assert g.call_count == 2


def test_does_not_retry_4xx():
    """4xx는 다시 걸어도 같은 답이다."""
    with patch("news.core.http.requests.get", return_value=_resp(404)) as g:
        assert http.get("https://e.com/x").status_code == 404
    assert g.call_count == 1


def test_does_not_retry_429():
    """429는 상대가 쉬라는 뜻이다 — 회차 안에서 조르지 않는다."""
    with patch("news.core.http.requests.get", return_value=_resp(429)) as g:
        http.get("https://e.com/x")
    assert g.call_count == 1


def test_retry_budget_is_capped():
    with patch("news.core.http.requests.get", return_value=_resp(503)) as g, \
         patch("news.core.http.time.sleep"):
        assert http.get("https://e.com/x").status_code == 503
    assert g.call_count == http.MAX_ATTEMPTS


def test_raises_after_exhausting_connection_errors():
    with patch("news.core.http.requests.get",
               side_effect=requests.ConnectionError("boom")) as g, \
         patch("news.core.http.time.sleep"):
        with pytest.raises(requests.RequestException):
            http.get("https://e.com/x")
    assert g.call_count == http.MAX_ATTEMPTS


def test_backoff_grows():
    waits = []
    with patch("news.core.http.requests.get", return_value=_resp(503)), \
         patch("news.core.http.time.sleep", side_effect=waits.append):
        http.get("https://e.com/x")
    assert waits == sorted(waits) and len(set(waits)) > 1, f"백오프가 커져야 한다: {waits}"
