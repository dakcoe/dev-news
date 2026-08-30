"""짧은 본문 폐기 문제 (keep-short-content).

재현하는 결함: MIN_CONTENT_CHARS = 200 하드 컷이 멀쩡히 뽑은 본문을 버려서
요약이 통째로 비었다. 실측 4건 — mastodon 툿 136자 2건, data4sci 119자,
phrack 75자(프래그먼트라 이건 버리는 게 맞다).

짧은 글은 원래 짧은 것이지 추출 실패가 아니다.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from news.core.enrich import MIN_CONTENT_CHARS, usable_content  # noqa: E402


def test_threshold_lowered():
    assert MIN_CONTENT_CHARS <= 100


def test_real_lengths_survive():
    """실측 추출 길이 — 136·136·119자는 살아야 한다."""
    for n in (136, 119, 100):
        assert usable_content("가" * n, description="") is not None, f"{n}자가 버려짐"


def test_too_short_still_dropped():
    """껍데기(쿠키 배너·내비게이션)를 막는 바닥값은 남긴다."""
    assert usable_content("가" * 75, description="") is None
    assert usable_content("", description="") is None
    assert usable_content(None, description="") is None


def test_shorter_than_description_is_dropped():
    """summarizer가 `content or description` 순으로 고른다 — 짧은 쪽이 이기면 안 된다."""
    assert usable_content("가" * 100, description="나" * 400) is None


def test_longer_than_description_wins():
    assert usable_content("가" * 500, description="나" * 400) is not None


def test_no_description_accepts_short_content():
    assert usable_content("가" * 120, description=None) is not None
