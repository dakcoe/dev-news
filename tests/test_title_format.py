"""번역제목 형식 회귀 테스트 (dedup-and-title-quality).

재현하는 결함: PROMPT가 저장소용으로 준 `"이름 — 한 줄 설명"` 형식을 모델이
문장형 제목에도 적용했다.

  TT : mvanhorn / last30days-skill
  KO : mvanhorn / last30days-skill — AI 에이전트 기반 검색 엔진, 사람을 검색하고
                                     투표·좋아요·실제 금액으로 평가
  SUM: … Claude, Codex, Cursor 등 50여 개 에이전트 스킬 호스트에서 설치 가능

제목의 설명과 요약이 서로 다른 물건을 가리켰다(요약 쪽이 README 근거로 맞다).
같은 원인으로 블로그 글 URL 슬러그를 저장소명처럼 붙인 사례도 나왔다 —
`anthropic / containment —`, `Mistral / Shieldstral —` (2026-08-06 배치).
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from news.summarizer import PROMPT, looks_like_identifier_title  # noqa: E402


# ------------------------------------------------- 제목 종류 판별
def test_repo_style_titles_are_identifiers():
    for t in ("mvanhorn / last30days-skill",
              "unclecode / crawl4ai",
              "checkstyle / checkstyle",
              "datasette-upload-dbs 0.5a0",
              "FLUX.1-Kontext-dev"):
        assert looks_like_identifier_title(t), f"고유명사 제목이어야 함: {t}"


def test_sentence_titles_are_not_identifiers():
    for t in ("Google DeepMind CEO Demis Hassabis is stepping down",
              "Delete Your padding-bottom Aspect-Ratio Hack",
              "As agents grow more capable, so does their potential blast radius",
              "Fair Work Commission condemns 'plain wrong' AI legal advice",
              "캘리포니아주 의회, 연령 확인법에서 Linux를 만장일치로 면제",
              "Why Erdős Problems Are Falling to AI"):
        assert not looks_like_identifier_title(t), f"문장형 제목이어야 함: {t}"


def test_slug_from_url_is_not_a_repo_name():
    """블로그 글 URL 슬러그는 저장소명이 아니다 — 8/6 배치의 실제 오출력."""
    for t in ("How we contain Claude",
              "Investigating three real-world incidents in our cybersecurity evaluations"):
        assert not looks_like_identifier_title(t)


# ------------------------------------------------- 프롬프트 규칙
def test_prompt_restricts_identifier_format_to_identifier_titles():
    """`이름 — 설명` 형식이 조건부라는 것이 프롬프트에 남아 있어야 한다."""
    assert "제목의 전부일 때만" in PROMPT


def test_prompt_forbids_format_on_sentence_titles():
    assert "문장형 제목" in PROMPT and "금지" in PROMPT


def test_prompt_still_forbids_raw_english_copy():
    """기존 제약(원제 영어 복사 금지)이 사라지지 않아야 한다."""
    assert "영어 그대로 복사" in PROMPT


def test_prompt_has_all_three_fields():
    for label in ("번역제목:", "요약:", "왜중요:"):
        assert label in PROMPT
