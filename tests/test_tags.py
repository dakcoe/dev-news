"""add-article-tags — 닫힌 어휘 태거 테스트 (SPEC 1B).

어휘는 news/core/tags.py의 VOCAB에 고정된다(LLM 자유 태그 생성 금지).
규칙 기반 매칭이므로 결정적이며, 실코퍼스 분포 검증(평균 3~4개)까지 여기서 한다.
"""
import json
import os

import pytest

from news.core import tags

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARD = os.path.join(ROOT, "data", "articles", "2026-08.json")


def test_vocab_integrity():
    """어휘 무결성: id는 kebab-case 유일, 라벨·패턴 필수."""
    ids = list(tags.VOCAB)
    assert len(ids) == len(set(ids))
    for tid, spec in tags.VOCAB.items():
        assert tid == tid.lower().strip()
        assert spec["label"], tid
        assert spec["patterns"] or tid in tags.IMPLIED_ONLY, tid
    # 암시 규칙의 대상 태그도 어휘 안에 있어야 한다
    for src, dst in tags.IMPLIES.items():
        assert src in tags.VOCAB and dst in tags.VOCAB


def test_ai_coding_article():
    a = {"title": "Auto mode is now the default in Claude Code for Pro plans",
         "source": "rss", "description": "", "summary": ""}
    got = tags.tag_article(a)
    assert "ai-coding" in got
    assert "ai" in got            # 세부 AI 태그 → 상위 ai 암시


def test_github_repo_implies_open_source():
    a = {"title": "vercel / next.js", "source": "github",
         "description": "The React Framework", "summary": ""}
    got = tags.tag_article(a)
    assert "open-source" in got
    assert "web" in got


def test_security_korean_text():
    a = {"title": "일부 x86 CPU의 하드웨어 백도어", "source": "geeknews",
         "description": "", "summary": ""}
    got = tags.tag_article(a)
    assert "security" in got
    assert "hardware" in got


def test_release_tag():
    a = {"title": "Jujutsu 0.44.0 릴리스", "source": "geeknews",
         "description": "", "summary": ""}
    assert "release" in tags.tag_article(a)


def test_no_match_returns_empty_not_crash():
    a = {"title": "완전히 무관한 제목", "source": "rss", "description": "", "summary": ""}
    assert tags.tag_article(a) == []


def test_dedup_and_order_stable():
    a = {"title": "LLM llm LLM agent", "source": "rss", "description": "llm", "summary": ""}
    got = tags.tag_article(a)
    assert len(got) == len(set(got))
    assert got == tags.tag_article(a)


@pytest.mark.skipif(not os.path.exists(SHARD), reason="실코퍼스 샤드 없음")
def test_corpus_distribution():
    """실코퍼스 검증: 평균 3.0~4.5개, 무태그 5% 미만 (EXEC_PLAN 완료 기준)."""
    with open(SHARD, encoding="utf-8") as f:
        arts = json.load(f)
    counts = [len(tags.tag_article(a)) for a in arts]
    avg = sum(counts) / len(counts)
    zero = sum(1 for c in counts if c == 0)
    assert 3.0 <= avg <= 4.5, f"평균 {avg:.2f}"
    assert zero / len(counts) < 0.05, f"무태그 {zero}/{len(counts)}"
