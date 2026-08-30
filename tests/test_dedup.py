"""중복 판정 회귀 테스트 (dedup-and-title-quality).

재현하는 결함: 중복 판정이 두 군데 다 완전일치였다.
  - build.py:dedupe          → URL 완전일치
  - scorer.py                → 정규화 제목 앞 60자 완전일치

그래서 같은 사건을 다른 소스가 물어오면 절대 만나지 않았다. 2026-08-30 배치에
캘리포니아 Linux 면제 기사가 hackernews(tomshardware) · geeknews(hada.io) 두 건으로
나란히 실렸고, 최근 196건 중 동일 기사 4쌍이 있었는데 cross_source_count>=2로
잡힌 건 2건뿐이었다.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from news.core.dedup import (  # noqa: E402
    normalize_url,
    title_similarity,
    merge_duplicates,
)


def _art(title, url, source="hackernews", score=0, **kw):
    return {"title": title, "url": url, "source": source, "score": score, **kw}


# ------------------------------------------------------------------ URL 정규화
def test_normalize_url_stnps_scheme_www_and_trailing_slash():
    same = {
        normalize_url("https://example.com/a-post"),
        normalize_url("http://example.com/a-post"),
        normalize_url("https://www.example.com/a-post"),
        normalize_url("https://example.com/a-post/"),
    }
    assert len(same) == 1


def test_normalize_url_drops_tracking_params_but_keeps_real_ones():
    a = normalize_url("https://e.com/p?utm_source=hn&utm_medium=web&id=7")
    b = normalize_url("https://e.com/p?id=7")
    assert a == b
    # 의미 있는 파라미터는 살아야 한다 — 긱뉴스 토픽 링크가 id로 구분된다
    assert normalize_url("https://news.hada.io/topic?id=1") != \
           normalize_url("https://news.hada.io/topic?id=2")


def test_normalize_url_drops_fragment():
    assert normalize_url("https://e.com/p#section") == normalize_url("https://e.com/p")


def test_normalize_url_survives_garbage():
    for bad in ("", None, "not a url", "javascript:void(0)"):
        normalize_url(bad)   # 예외를 던지지 않기만 하면 된다


# ------------------------------------------------------------------ 제목 유사도
def test_identical_titles_are_similar():
    assert title_similarity("Please stop flooding our projects with AI slop",
                            "Please stop flooding our projects with AI slop") == 1.0


def test_near_identical_titles_cross_threshold():
    # 실측 쌍 (rss ⇄ hackernews), 자카드 0.8
    a = "Just a rumour of a bug is enough to find a security exploit"
    b = "Just the rumour of a bug is enough to find an exploit that works"
    assert title_similarity(a, b) >= 0.6


def test_unrelated_titles_are_not_similar():
    a = "Rust Function Overloading - Call for Experimentation"
    b = "Delta encoding multiplayer game state"
    assert title_similarity(a, b) < 0.6


def test_korean_titles_do_not_falsely_merge():
    """한국어는 토큰이 겹치지 않아 유사도로 잡을 수 없다. 잘못 합치지만 않으면 된다.

    실측에서 {'debian'} vs {'debian'} 같은 한 토큰짜리 교집합이 1.0으로 나와
    서로 다른 기사가 합쳐질 뻔했다 — 토큰이 너무 적으면 판정을 포기해야 한다.
    """
    a = "Debian과 세이렌"
    b = "Debian, 생성형 AI의 '책임 있는 사용'을 허용하기로 결정"
    assert title_similarity(a, b) < 0.6


def test_too_few_tokens_never_merges():
    assert title_similarity("Go 1.26", "Go 1.27") < 0.6


# ------------------------------------------------------------------ 병합
def test_merge_by_url_keeps_higher_score():
    got = merge_duplicates([
        _art("A post", "https://e.com/p", "hackernews", score=10),
        _art("A post", "https://www.e.com/p/", "lobsters", score=99),
    ])
    assert len(got) == 1
    assert got[0]["score"] == 99


def test_merge_by_title_across_sources():
    got = merge_duplicates([
        _art("Please stop flooding our projects with AI slop",
             "https://a.com/x", "hackernews", score=50),
        _art("Please stop flooding our projects with AI slop",
             "https://b.com/y", "lobsters", score=5),
    ])
    assert len(got) == 1


def test_merge_sets_cross_source_count():
    got = merge_duplicates([
        _art("Qwen3.8-Flash-Next: A New Architecture", "https://a.com/x", "hackernews"),
        _art("Qwen3.8-Flash-Next: A New Architecture", "https://b.com/y", "rss"),
    ])
    assert got[0]["cross_source_count"] == 2


def test_same_source_twice_is_not_two_sources():
    got = merge_duplicates([
        _art("Same headline here for testing", "https://a.com/x", "geeknews"),
        _art("Same headline here for testing", "https://b.com/y", "geeknews"),
    ])
    assert got[0]["cross_source_count"] == 1


def test_distinct_articles_all_survive():
    arts = [
        _art("Rust Function Overloading - Call for Experimentation", "https://a.com/1"),
        _art("Delta encoding multiplayer game state", "https://a.com/2"),
        _art("40 Lines of Go That Cut Our LLM Bill by 71%", "https://a.com/3"),
    ]
    assert len(merge_duplicates(arts)) == 3


def test_merged_keeps_all_source_names():
    got = merge_duplicates([
        _art("Boot a Virtual iPhone via Apple Virtualization framework",
             "https://a.com/x", "hackernews", score=1),
        _art("Boot a Virtual iPhone via Apple Virtualization framework",
             "https://b.com/y", "geeknews", score=9),
    ])
    assert set(got[0]["merged_sources"]) == {"hackernews", "geeknews"}


def test_empty_input():
    assert merge_duplicates([]) == []


# ------------------------------------------------------------------ 오병합 가드
# 8월 전체 1,272건(비교 80만 쌍)을 돌려 실제로 잘못 합쳐질 뻔한 쌍들이다.
def test_different_versions_never_merge():
    for a, b in (("sqlite-utils 4.2.1", "sqlite-utils 4.2"),
                 ("llm-anthropic 0.27", "llm-anthropic 0.26"),
                 ("alchemy-utils 0.1a1", "alchemy-utils 0.1a0")):
        assert title_similarity(a, b) < 0.6, f"다른 릴리스인데 합쳐짐: {a} / {b}"


def test_same_version_still_merges():
    assert title_similarity("Chicken Scheme 6.0", "Chicken Scheme 6.0 released") >= 0.6


def test_different_repos_never_merge():
    assert title_similarity("anthropics / claude-plugins-official",
                            "anthropics / claude-plugins-community") < 0.6


def test_site_prefix_does_not_create_similarity():
    """Show GN 접두사만 겹치는 서로 다른 글."""
    a = "Show GN: homebutler - 홈서버 관리에 필요한 걸 한 바이너리에 담고 AI까지"
    b = "Show GN: 공공데이터 통합검색 x AI"
    assert title_similarity(a, b) < 0.6


def test_korean_articles_about_same_product_do_not_merge():
    """제품명 조각만 겹치는 서로 다른 한국어 글 — 실측 0.67이었다."""
    a = "GPT-5.6 Sol 가격 50% 인하"
    b = "GPT-5.6 Sol은 OpenAI가 지금까지 출시한 최고의 비전 모델"
    assert title_similarity(a, b) < 0.6


def test_cross_language_pair_still_allowed():
    """한쪽만 한국어인 쌍에는 한국어 가드를 적용하지 않는다 — 잡아야 하는 쌍이다."""
    a = "Claude Code, Auto mode를 기본 권한 모드로 전환"
    b = "Auto mode is now the default in Claude Code"
    assert title_similarity(a, b) >= 0.6
