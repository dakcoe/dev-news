"""요약 산출물 채점 (add-summary-quality-eval).

왜 필요한가 — 모델 교체(llama-3.3-70b → gpt-oss-120b) 때 품질 판정이 사람 눈이
전부였다. `LLM_MODEL`은 Actions Variables로 코드 수정 없이 바뀌므로, 누가 바꿔서
나빠져도 알 방법이 없었다.

LLM을 부르지 않는 순수 함수만 둔다. 실제 모델을 태우는 건 scripts/eval_summary.py다.
덕분에 채점기 자체는 API 키 없이 CI에서 항상 검증된다.

지표는 전부 **실측된 결함**에서 나왔다. 추측으로 만든 규칙은 넣지 않는다 —
오탐이 나면 정상 산출물을 버리게 되고, 그게 FOREIGN_RE에서 이미 한 번 있었다.
"""
from __future__ import annotations

import re

from news.summarizer import FOREIGN_RE

MIN_SUMMARY = 60
MAX_SUMMARY = 500
MIN_HANGUL_RATIO = 0.15

HANGUL_RE = re.compile(r"[가-힣]")
WORD_RE = re.compile(r"[0-9A-Za-z가-힣]+")

# "없음"이 문장 안에 남은 경우. summarizer._strip_no_info_tail이 꼬리는 떼지만
# 중간에 박히면 남는다 ("기술 스택 정보는 없음. 다만 …").
NOINFO_RE = re.compile(r"(?<![가-힣])없음(?![가-힣])")

# 본문이 그대로 샌 흔적. 요약에 코드펜스나 링크가 있으면 요약이 아니다.
RESIDUE_RE = re.compile(r"```|https?://|\|\s*-{3,}\s*\||^\s*[-*]\s+", re.MULTILINE)


def _hangul_ratio(text: str) -> float:
    letters = [c for c in text if c.isalnum()]
    if not letters:
        return 1.0                       # 판정 불가 — 통과로 본다
    return len(HANGUL_RE.findall(text)) / len(letters)


def echo_ratio(title: str, summary: str) -> float:
    """요약이 원제 어절을 얼마나 되풀이하는지 (SPEC 1.3 '제목 복창 금지').

    GitHub 저장소 항목은 프롬프트가 'owner / repo — 설명' 형태를 요구해 구조적으로
    제목을 반복한다. 그래서 하드 판정에서 빼고 참고 수치로만 쓴다.
    """
    words = {w.lower() for w in WORD_RE.findall(title) if len(w) > 1}
    if not words:
        return 0.0
    body = summary.lower()
    return sum(1 for w in words if w in body) / len(words)


def check(article: dict) -> list[str]:
    """한 기사의 요약 산출물에서 발견된 문제 코드 목록. 정상이면 빈 리스트."""
    ko = (article.get("ko_title") or "").strip()
    summary = (article.get("summary") or "").strip()
    why = (article.get("why") or "").strip()
    joined = " ".join(filter(None, [ko, summary, why]))
    issues = []

    if not ko or not summary:
        issues.append("incomplete")

    if joined and FOREIGN_RE.search(joined):
        issues.append("foreign")

    if ko and _hangul_ratio(ko) < MIN_HANGUL_RATIO:
        issues.append("untranslated")

    if NOINFO_RE.search(joined):
        issues.append("noinfo-leak")

    if summary and not (MIN_SUMMARY <= len(summary) <= MAX_SUMMARY):
        issues.append("length")

    if RESIDUE_RE.search(summary) or RESIDUE_RE.search(why):
        issues.append("residue")

    return issues


CHECKS = ("incomplete", "foreign", "untranslated", "noinfo-leak", "length", "residue")


def score(articles: list[dict]) -> dict:
    """전체 채점. 지표별 통과율과 문제 기사 목록을 돌려준다."""
    n = len(articles)
    failures: dict[str, list[str]] = {c: [] for c in CHECKS}
    clean = 0
    echoes = []

    for a in articles:
        issues = check(a)
        if not issues:
            clean += 1
        for code in issues:
            failures[code].append(a.get("title", "")[:60])
        echoes.append(echo_ratio(a.get("title", ""), a.get("summary") or ""))

    return {
        "count": n,
        "clean_rate": round(clean / n, 3) if n else 0.0,
        "pass_rate": {c: round((n - len(v)) / n, 3) if n else 0.0
                      for c, v in failures.items()},
        "failures": {c: v for c, v in failures.items() if v},
        "echo_mean": round(sum(echoes) / n, 3) if n else 0.0,
    }


def compare(current: dict, baseline: dict, tolerance: float = 0.10) -> list[str]:
    """기준선 대비 회귀 목록. 온도가 0이 아니라 실행마다 결과가 다르므로
    정확값이 아니라 허용 오차를 둔다."""
    out = []
    for code in CHECKS:
        now = current["pass_rate"].get(code, 0.0)
        was = baseline.get("pass_rate", {}).get(code, 0.0)
        if now < was - tolerance:
            out.append(f"{code}: {was:.0%} → {now:.0%}")
    now, was = current["clean_rate"], baseline.get("clean_rate", 0.0)
    if now < was - tolerance:
        out.append(f"clean_rate: {was:.0%} → {now:.0%}")
    return out
