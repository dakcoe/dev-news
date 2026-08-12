"""요약 채점기 회귀 테스트 (add-summary-quality-eval).

지표는 전부 실측된 결함에서 나왔다. 추측으로 만든 규칙은 넣지 않는다 —
오탐이 나면 정상 산출물을 버리게 되고, FOREIGN_RE에서 이미 한 번 겪었다
(U+202F 공백과 →를 "외국 문자"로 잡아 재생성·미게시를 유발할 뻔했다).
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from news.core import quality  # noqa: E402
from news.core.redact import PATTERNS  # noqa: E402

CORPUS = os.path.join(ROOT, "tests", "golden", "corpus.json")

GOOD = {
    "title": "Go is an ideal language for AI-assisted software engineering",
    "ko_title": "Go 언어가 AI 기반 소프트웨어 엔지니어링에 이상적인 이유",
    "summary": ("AI가 대량의 코드를 생성하면서 개발 병목이 코드 작성에서 리뷰·검증으로 "
                "이동하고 있다. Go는 단순 문법과 정적 타입, 표준 도구를 하나로 묶어 "
                "AI가 만든 코드를 빠르게 검증하게 해준다."),
    "why": "AI 코드 생성 시 검증 루프를 효율화해 생산성을 높인다.",
}


def _bad(**over):
    return {**GOOD, **over}


# ------------------------------------------------------ 정상은 통과
def test_good_article_has_no_issues():
    assert quality.check(GOOD) == []


def test_benign_symbols_not_flagged():
    """FOREIGN_RE 오탐 재발 방지 — 화살표·좁은 공백은 결함이 아니다."""
    assert quality.check(_bad(ko_title="SVG→PDF 변환기 공개", summary=GOOD["summary"])) == []


# ------------------------------------------------------ 실측 결함 4종
def test_untranslated_title_caught():
    """실측: gpt-oss가 'React useEventSource Hook: Server-Sent Events…'를 그대로 뒀다."""
    issues = quality.check(_bad(ko_title="React useEventSource Hook: Server-Sent Events"))
    assert "untranslated" in issues


def test_foreign_script_caught():
    """실측: llama 계열이 한자·가나를 섞었다."""
    assert "foreign" in quality.check(_bad(summary="이 기능은 超越적이다. " + GOOD["summary"]))
    assert "foreign" in quality.check(_bad(why="プロトタイプ 단계다."))


def test_noinfo_leak_caught():
    """실측: 정상 요약 뒤에 '기술 스택 정보는 없음.'을 덧붙였다."""
    assert "noinfo-leak" in quality.check(_bad(why="기술 스택 정보는 없음. 다만 유용하다."))


def test_residue_caught():
    """본문이 그대로 샌 흔적 — 코드펜스·링크가 있으면 요약이 아니다."""
    assert "residue" in quality.check(_bad(summary="```sh\nmake -j8\n```" + GOOD["summary"]))
    assert "residue" in quality.check(_bad(summary=GOOD["summary"] + " 자세히는 https://x.com/a 참고"))


# ------------------------------------------------------ 형식 결함
def test_length_bounds():
    assert "length" in quality.check(_bad(summary="짧다."))
    assert "length" in quality.check(_bad(summary="가" * 501))
    assert "length" not in quality.check(_bad(summary="가" * 200))


def test_incomplete_fields():
    assert "incomplete" in quality.check(_bad(ko_title=""))
    assert "incomplete" in quality.check(_bad(summary=""))


def test_repo_style_title_passes():
    """GitHub 항목은 'owner / repo — 한 줄 설명' 형태가 정상이다."""
    assert "untranslated" not in quality.check(
        _bad(ko_title="cathrynlavery / diagram-design — 편집자 수준 다이어그램 생성 도구"))


# ------------------------------------------------------ 집계·비교
def test_score_aggregates():
    r = quality.score([GOOD, _bad(ko_title="Plain English Title Here")])
    assert r["count"] == 2
    assert r["clean_rate"] == 0.5
    assert r["pass_rate"]["untranslated"] == 0.5
    assert "untranslated" in r["failures"]


def test_compare_flags_regression():
    base = {"clean_rate": 1.0, "pass_rate": {c: 1.0 for c in quality.CHECKS}}
    now = {"clean_rate": 0.5, "pass_rate": {**{c: 1.0 for c in quality.CHECKS}, "foreign": 0.5}}
    regs = quality.compare(now, base)
    assert any("foreign" in r for r in regs) and any("clean_rate" in r for r in regs)


def test_compare_tolerates_noise():
    """온도가 0이 아니라 실행마다 조금씩 다르다 — 소폭 변동은 회귀가 아니다."""
    base = {"clean_rate": 1.0, "pass_rate": {c: 1.0 for c in quality.CHECKS}}
    now = {"clean_rate": 0.95, "pass_rate": {c: 0.95 for c in quality.CHECKS}}
    assert quality.compare(now, base, tolerance=0.10) == []


def test_echo_ratio():
    assert quality.echo_ratio("Go is ideal for AI", "Go is ideal for AI 라고 한다") > 0.9
    assert quality.echo_ratio("Go is ideal for AI", "전혀 다른 내용이다") < 0.3


# ------------------------------------------------------ 골든 코퍼스
def test_golden_corpus_shape():
    rows = json.load(open(CORPUS, encoding="utf-8"))
    assert len(rows) >= 10
    assert {r["source"] for r in rows} >= {"geeknews", "github", "rss"}   # 유형이 섞여야 의미 있다
    for r in rows:
        assert r["title"] and r["content"]


def test_golden_corpus_has_no_secrets():
    """커밋되는 픽스처다 — 시크릿이 남으면 이 파일 자체가 push protection에 걸린다."""
    raw = open(CORPUS, encoding="utf-8").read()
    for name, pattern in PATTERNS:
        assert not pattern.search(raw), name
