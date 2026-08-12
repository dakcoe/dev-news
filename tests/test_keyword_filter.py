"""키워드 필터 회귀 테스트 (fix-keyword-filter-boundary).

재현하는 결함: `any(k in text)` 부분문자열 매칭이라 3글자 이하 키워드가 아무 영어
단어에나 걸렸다 — "said"의 ai, "ago"의 go, "legitimate"의 git. 실측으로 미신뢰
출처 기사 167건 중 166건(99%)이 통과해 필터가 사실상 없는 것과 같았다.
"""
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from build import keyword_filter  # noqa: E402

KW = ["ai", "go", "git", "api", "cli", "container", "release", "agent",
      "machine learning", "security", "python"]


def _art(title, source="hackernews", description=""):
    return {"title": title, "source": source, "description": description}


def _passes(title, keywords=None, source="hackernews"):
    kept = keyword_filter([_art(title, source)], keywords or KW)
    return len(kept) == 1


# --------------------------------------------------- 부분문자열 오탐 (이번 버그)
def test_substring_false_positives_blocked():
    for title in ("She said the weather was nice today",
                  "A cat video went viral again",
                  "Ago, a legitimate email chain about digits",
                  "The brain may be about to have its Ozempic moment",
                  "Tuxedo No. 2 - Cocktail recipes"):
        assert not _passes(title), f"통과하면 안 됨: {title}"


def test_short_keyword_tense_suffix_still_blocked():
    """3글자 이하에 시제 어미까지 허용하면 going(go+ing)·aid(ai+d)가 다시 샌다."""
    assert not _passes("I am going to the store")
    assert not _passes("Foreign aid budget cuts")
    assert not _passes("It goes without saying")


# --------------------------------------------------- 정상 통과
def test_exact_and_plural_forms_pass():
    for title in ("Go is an ideal language for AI",
                  "Firefox Containers Preview",
                  "Chicken Scheme 6.0 released",
                  "Stealing Reasoning Traces from Proprietary LLM APIs",
                  "Agents are eating the web",
                  "Machine learning in production"):
        assert _passes(title), f"통과해야 함: {title}"


def test_hyphen_and_punctuation_boundaries():
    assert _passes("gpt-5 is out", keywords=["gpt"])
    assert _passes("Deep dive: api design", keywords=["api"])
    assert not _passes("rapid prototyping", keywords=["api"])


def test_korean_titles_unaffected():
    """한글은 영숫자가 아니라 경계 조건이 항상 성립한다."""
    assert _passes("파이썬 3.14 릴리스 — python 성능 개선")
    assert not _passes("서울 지하철 요금 인상 안내")


# --------------------------------------------------- 기존 계약 유지
def test_trusted_sources_bypass_filter():
    for src in ("github", "devto", "geeknews", "rss", "anthropic"):
        assert _passes("Tuxedo No. 2 - Cocktail recipes", source=src), src


def test_empty_keywords_passes_everything():
    assert keyword_filter([_art("아무 제목")], []) == [_art("아무 제목")]


def test_description_is_searched_too():
    kept = keyword_filter([_art("Weekly roundup", description="a new python release")], KW)
    assert len(kept) == 1


# --------------------------------------------------- 실제 설정 검수
def test_shipped_config_blocks_known_noise():
    """config.yaml의 실제 어휘로 HN 잡음이 걸러지는지."""
    kw = yaml.safe_load(open(os.path.join(ROOT, "config.yaml"), encoding="utf-8"))["keywords"]
    noise = ("Tuxedo No. 2 - Cocktail recipes",
             "Melatonin impairs morning cognition in healthy young adults",
             "Confessions of a Long-Distance Sailor",
             "World Train Map - 1247 train routes around the world")
    dev = ("pg_clickhouse v0.10: Subquery pushdown and 1000x faster TPC-H queries",
           "What I learned by putting GitHub Copilot behind a MitM proxy",
           "OpenAI and Anthropic hidden CoT leaks when given deep_think tool",
           "OpenChamber: An Agentic Development Environment")
    for t in noise:
        assert not _passes(t, kw), f"잡음이 통과: {t}"
    for t in dev:
        assert _passes(t, kw), f"개발 기사가 차단: {t}"
