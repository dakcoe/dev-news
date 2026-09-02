"""태그 정밀도 (fix-tag-assignment).

재현하는 결함: 태거가 `제목+ko_title+설명+요약`에 정규식을 돌리는데, 요약은
LLM이 쓴 부연이라 본문 주제와 먼 단어가 흔하다. 범용 한국어 명사가 스치듯
등장해 태그가 됐다 — 단독으로 태그를 만든 패턴 상위가 전부 범용어였다
(공개 114 · 도구 136 · 연구 68 · 서버 53 · 기업 33).

실측 오배정:
  padding-bottom aspect-ratio (CSS) → security  ← 요약의 "해킹"
  Delta encoding multiplayer game   → science   ← 요약의 "은하"(게임 세계관)
                                    → release   ← 요약의 "업데이트"
  checkstyle (Java 린터)            → web       ← 요약의 "html"(문서 형식)
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from news.core.tags import tag_article  # noqa: E402


def _t(title="", ko_title="", description="", summary="", source=""):
    return tag_article({"title": title, "ko_title": ko_title,
                        "description": description, "summary": summary,
                        "source": source})


# ------------------------------------------------------ 실측 오배정이 사라질 것
def test_generic_word_in_summary_does_not_tag():
    tags = _t(title="Delta encoding multiplayer game state",
              ko_title="멀티플레이어 게임 상태 델타 인코딩",
              description="Old Light is a browser-based strategy game.",
              summary="클라이언트는 자신이 볼 수 있는 은하 상태 전체를 보관하고 "
                      "서버는 변경 사항을 패치로 전송한다. 업데이트가 잦다.")
    assert "science" not in tags, "요약의 '은하'로 과학 태그가 붙으면 안 된다"
    assert "release" not in tags, "요약의 '업데이트'로 릴리스 태그가 붙으면 안 된다"


def test_document_format_mention_does_not_tag_web():
    tags = _t(title="checkstyle / checkstyle",
              ko_title="checkstyle — Java 코드 품질 검사 도구",
              description="Checkstyle is a tool for checking Java source code.",
              summary="최신 릴리스는 HTML 형식의 문서와 CI 연동 배지를 지원한다.")
    assert "web" not in tags, "요약의 'html'로 web 태그가 붙으면 안 된다"


def test_hack_as_trick_is_not_security():
    """`hack(ed|ing|er)?`의 `?` 때문에 '요령'을 뜻하는 hack이 보안이 됐다."""
    tags = _t(title="Delete Your padding-bottom Aspect-Ratio Hack",
              ko_title="패딩-bottom 비율 해킹 삭제",
              description="The old CSS trick for 16:9 boxes is no longer needed.",
              summary="최신 CSS에서는 aspect-ratio 속성으로 한 줄이면 된다.")
    assert "security" not in tags
    assert "web" in tags, "CSS 기사이므로 web은 유지돼야 한다"


def test_real_hacking_still_tagged():
    assert "security" in _t(title="A hacker breached the build server")
    assert "security" in _t(title="Hacking the firmware update process")


# --------------------------------------------------- 정당한 태그는 유지될 것
def test_proper_nouns_still_match_anywhere():
    """고유명사는 설명·요약에서도 잡혀야 한다 — 제목이 짧은 기사가 많다."""
    assert "llm" in _t(title="Debian과 세이렌",
                       description="Debian은 투표를 통해 LLM 사용을 허용하기로 했다.")
    assert "ai" in _t(title="Some short title",
                      summary="OpenAI가 새 모델을 공개했다.")


def test_generic_word_in_title_is_accepted():
    """약한 패턴도 출처가 준 원제목에 있으면 그 기사의 주제다."""
    assert "release" in _t(title="Chicken Scheme 6.0 공개")
    assert "dev-tools" in _t(title="새 빌드 도구 소개")


def test_generic_word_only_in_llm_title_does_not_tag():
    """ko_title은 LLM이 만든 글이다 — 오역이 태그를 만들면 안 된다."""
    assert "security" not in _t(title="Delete Your Aspect-Ratio Hack",
                                ko_title="비율 해킹 삭제")


def test_no_tag_cap_cross_topic_article():
    """2026-08-31 zhaoxuya520 / reverse-skill — 8개 태그가 매칭됐는데 상한 4개에서
    VOCAB 앞쪽 AI 그룹만 남고 security·open-source가 잘려 나갔다. 상한을 두지 않는다."""
    got = _t(title="zhaoxuya520 / reverse-skill", ko_title="리버스-스킬",
             description="Reverse Engineering / Authorized Penetration Testing / "
                         "Security Research Skill Router Pack AI-powered routing "
                         "Supports Claude Code, Kiro, Cursor, Cline, and other AI coding clients",
             summary="reverse-skill은 사이버보안 스킬을 라우팅하는 패키지이며 현재 v1.0.1이 "
                     "릴리스되었다. MIT 라이선스로 배포된다.",
             source="github")
    for tid in ("ai", "llm", "ai-agent", "ai-coding", "research", "security",
                "open-source", "release"):
        assert tid in got, (tid, got)
    assert len(got) == 8


def test_empty_article():
    assert _t() == []


# ------------------------------------------------- 중의적 어휘 (fix-inference-tag)
def test_type_inference_is_not_llm():
    """로컬 전체 실행에서 발견 — TypeScript의 타입 추론이 LLM 태그를 만들었다.

    colinhacks / zod → ai, llm, web, open-source
    "TypeScript-first schema validation with static type inference"
    """
    tags = _t(title="colinhacks / zod",
              description="TypeScript-first schema validation with static type inference",
              summary="TypeScript-first schema validation with static type inference")
    assert "llm" not in tags
    assert "ai" not in tags, "llm이 IMPLIES로 ai까지 끌고 왔다"


def test_inference_in_title_is_still_llm():
    """추론 최적화는 이 피드의 핵심 주제다 — 제목에 있으면 잡아야 한다."""
    assert "llm" in _t(title="A fast inference engine for local models")
    assert "llm" in _t(title="추론 속도를 3배 높인 방법")
