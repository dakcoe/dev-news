"""빈 요약 폴백 문구 테스트 (fix-empty-summary-label).

본문 추출 불가(페이월·영상·JS 전용 페이지) 기사는 LLM이 "덧붙일 것 없음"으로
답해 summary가 비는데, 이는 생성 실패가 아니다. 폴백 문구가 상황을 정확히
설명하는지 확인한다.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from news.render import to_view_model  # noqa: E402


def _article(**over):
    base = {"title": "t", "url": "https://x/1", "source": "hackernews",
            "summary": "", "description": "", "why": "중요하다."}
    return {**base, **over}


def test_empty_summary_shows_no_body_notice():
    vm = to_view_model([_article()])[0]
    assert "본문이 공개되지 않은 기사" in vm["body"]
    assert "생성 실패" not in vm["body"]


def test_normal_summary_untouched():
    vm = to_view_model([_article(summary="요약 문장이다.")])[0]
    assert vm["body"] == "<p>요약 문장이다.</p>"


def test_description_fallback_before_notice():
    vm = to_view_model([_article(description="피드 설명.")])[0]
    assert vm["body"] == "<p>피드 설명.</p>"
