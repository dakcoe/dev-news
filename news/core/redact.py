"""수집물에 섞여 들어온 남의 API 토큰을 마스킹한다.

왜 필요한가 — 이 저장소는 기사 본문(`content`)과 제목·요약을 그대로 커밋한다.
남의 글이나 GitHub README에 진짜 액세스 토큰이 박혀 있으면 그게 그대로
`data/articles/YYYY-MM.json`·`data/candidates/YYYY-MM.json`에 실려 push되고,
GitHub Push Protection이 `GH013`으로 push를 거부해 워크플로우가 통째로 죽는다
(2026-08-12 01:02 KST run 31510062957 — Hugging Face 토큰).

차단이 아니라 마스킹이다. 기사는 그대로 게시되고 토큰 문자열만 `[REDACTED]`로
가려진다 — 무엇을 숨길지는 열람 단계가 정한다는 SPEC 1.1과 충돌하지 않는다.

패턴은 GitHub 시크릿 스캐닝이 실제로 차단하는 공급자를 우선으로 담았다. 새 공급자를
추가할 때는 접두사가 뚜렷하고 길이 하한이 있는 것만 넣는다 — 오탐으로 본문을 훼손하면
요약 품질이 떨어진다.
"""
from __future__ import annotations

import re

PLACEHOLDER = "[REDACTED]"

# 좁은 것부터 넓은 것 순. 어느 쪽이 먼저 걸려도 결과 문자열은 같지만,
# 로그에 찍히는 공급자 이름이 정확해진다.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private_key", re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----")),
    ("huggingface", re.compile(r"\bhf_[A-Za-z0-9]{30,}")),
    ("huggingface_org", re.compile(r"\bapi_org_[A-Za-z0-9]{30,}")),
    ("anthropic", re.compile(r"\bsk-ant-[A-Za-z0-9\-_]{24,}")),
    ("openrouter", re.compile(r"\bsk-or-v1-[A-Za-z0-9]{32,}")),
    ("openai", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9\-_]{32,}")),
    ("stripe", re.compile(r"\b[sr]k_live_[A-Za-z0-9]{20,}")),
    ("groq", re.compile(r"\bgsk_[A-Za-z0-9]{40,}")),
    ("github_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}")),
    ("aws_key_id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("slack", re.compile(r"\bxox[baprse]-[0-9A-Za-z\-]{10,}")),
    ("sendgrid", re.compile(r"\bSG\.[A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-]{16,}")),
    ("npm", re.compile(r"\bnpm_[A-Za-z0-9]{36}\b")),
    ("telegram_bot", re.compile(r"\b\d{8,10}:AA[A-Za-z0-9_\-]{32,}")),
]


def redact_text(text: str, stats: dict[str, int] | None = None) -> str:
    """문자열에서 토큰처럼 보이는 부분을 `[REDACTED]`로 바꾼다."""
    for kind, pattern in PATTERNS:
        text, n = pattern.subn(PLACEHOLDER, text)
        if n and stats is not None:
            stats[kind] = stats.get(kind, 0) + n
    return text


def _scrub(value, stats: dict[str, int]):
    if isinstance(value, str):
        return redact_text(value, stats)
    if isinstance(value, dict):
        return {k: _scrub(v, stats) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v, stats) for v in value]
    return value                                    # int·bool·None·float은 그대로


def redact_articles(articles: list[dict], stage: str = "") -> list[dict]:
    """기사 목록의 모든 문자열 값을 마스킹한 새 목록을 돌려준다 (입력은 불변)."""
    stats: dict[str, int] = {}
    out = [_scrub(a, stats) for a in articles]
    if stats:
        detail = " · ".join(f"{k} {v}" for k, v in sorted(stats.items()))
        label = f"{stage} " if stage else ""
        print(f"[redact] {label}시크릿 {sum(stats.values())}건 마스킹 ({detail})")
    return out
