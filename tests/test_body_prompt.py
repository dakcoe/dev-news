"""요약 프롬프트에 넣는 본문 (summarizer._body_for_prompt).

본문을 못 가져온 기사를 댓글로 메우지 않는다. 익명 의견이 기사 내용처럼 요약되고,
사람 검토 없이 게시되면 정보통신망법 제44조의10(과실 배상)에 걸린다.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from news import summarizer as S  # noqa: E402


def test_보통_본문은_그대로_2천자():
    assert S._body_for_prompt({}, "x" * 3000) == "x" * 2000
    assert S._body_for_prompt({}, "") == S.NO_BODY


def test_두_프롬프트가_같은_헬퍼를_쓴다():
    src = open(os.path.join(ROOT, "news", "summarizer.py"), encoding="utf-8").read()
    assert src.count("_body_for_prompt(article, body)") == 2
    assert "(본문 없음 — 제목과 요약만으로" not in src


def test_댓글로_본문을_메우지_않는다():
    src = open(os.path.join(ROOT, "build.py"), encoding="utf-8").read()
    assert 'redact_articles(enrich(picked), "본문")' in src
    assert "fill_from_discussion" not in src
    assert not os.path.exists(os.path.join(ROOT, "news", "core", "discussion.py"))
