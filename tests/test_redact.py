"""수집물 시크릿 마스킹 회귀 테스트.

재현하는 실패: 2026-08-12 01:02 KST 워크플로우(run 31510062957)가 `변경분 커밋`에서
죽었다. 수집한 기사 본문에 남의 Hugging Face 액세스 토큰이 박혀 있었고, GitHub
Push Protection이 `docs/data/articles/2026-08.json:311`을 지목하며 push를 거부했다.

주의 — 이 파일에는 토큰 문자열 리터럴을 절대 적지 않는다. 적으면 이 테스트 파일
자체가 push protection에 걸린다. 샘플은 전부 런타임 문자열 결합으로 만든다.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from news.core import archive, candidates  # noqa: E402
from news.core.redact import redact_articles, redact_text  # noqa: E402

KST = timezone(timedelta(hours=9))

# 패턴만 맞춘 가짜 샘플 (리터럴이 아니라 결합으로 생성)
HF_TOKEN = "hf_" + "K" * 37
SAMPLES = {
    "huggingface": HF_TOKEN,
    "huggingface_org": "api_org_" + "L" * 34,
    "anthropic": "sk-ant-api03-" + "m" * 40,
    "openrouter": "sk-or-v1-" + "n" * 64,
    "openai": "sk-proj-" + "o" * 48,
    "groq": "gsk_" + "p" * 48,
    "github_pat": "github_pat_" + "q" * 60,
    "github_token": "ghp_" + "r" * 36,
    "aws_key_id": "AKIA" + "S" * 16,
    "google_api_key": "AIza" + "t" * 35,
    "slack": "xoxb-" + "1" * 12 + "-" + "u" * 24,
    "stripe": "sk_live_" + "v" * 24,
    "sendgrid": "SG." + "w" * 22 + "." + "x" * 43,
    "npm": "npm_" + "y" * 36,
    "telegram_bot": "1234567890:AA" + "z" * 33,
    "private_key": (
        "-----BEGIN RSA PRIVATE KEY-----\n" + "MIIE" * 20 + "\n-----END RSA PRIVATE KEY-----"
    ),
}


@pytest.mark.parametrize("kind", sorted(SAMPLES))
def test_provider_tokens_masked(kind):
    secret = SAMPLES[kind]
    out = redact_text(f"설정하려면 {secret} 를 환경변수에 넣으세요.")
    assert secret not in out
    assert "[REDACTED]" in out


def test_hugging_face_token_in_readme_masked():
    """이번 실패의 직접 재현 — GitHub README 본문에 박힌 HF 토큰."""
    body = f"```sh\nexport HF_TOKEN={HF_TOKEN}\nhuggingface-cli login\n```"
    out = redact_text(body)
    assert HF_TOKEN not in out
    assert "huggingface-cli login" in out          # 나머지 본문은 보존


def test_plain_text_untouched():
    """오탐 회귀 — 정상 본문은 한 글자도 건드리지 않는다."""
    text = (
        "토스의 QA 플랫폼 토션(Tossion)을 소개합니다.\n"
        "https://github.com/antirez/h3.c 를 참고하세요.\n"
        "```sh\nmake -j8\n./h3 --info -d ./MiniMax-H3\n```\n"
        "task-management-and-deployment-automation-pipeline\n"
        "커밋 665609e69ff7adb17ce49792b72d9dd6d17506ee 기준."
    )
    assert redact_text(text) == text


def test_non_string_and_nested_values_preserved():
    articles = [{
        "url": "https://example.com/a",
        "upvotes": 221,
        "page": True,
        "content": None,
        "tags": ["ai", "llm"],
        "native": {"stars": 100, "note": f"key={SAMPLES['groq']}"},
    }]
    out = redact_articles(articles)
    assert out[0]["upvotes"] == 221
    assert out[0]["page"] is True
    assert out[0]["content"] is None
    assert out[0]["tags"] == ["ai", "llm"]
    assert out[0]["native"]["stars"] == 100
    assert SAMPLES["groq"] not in out[0]["native"]["note"]


def test_redact_articles_does_not_mutate_input():
    original = [{"url": "https://a", "content": f"토큰: {HF_TOKEN}"}]
    redact_articles(original)
    assert HF_TOKEN in original[0]["content"]      # 원본은 그대로, 새 리스트를 반환


def test_archive_shard_has_no_secret(tmp_path):
    """마스킹을 거친 기사는 커밋 대상 파일에 토큰 원문을 남기지 않는다."""
    base = str(tmp_path / "articles")
    now = datetime(2026, 8, 12, 1, 2, tzinfo=KST)
    picked = redact_articles([{
        "url": "https://github.com/foo/bar",
        "title": "bar",
        "content": f"# bar\n\nexport HF_TOKEN={HF_TOKEN}\n",
    }])
    archive.append(picked, now, base_dir=base)

    raw = open(os.path.join(base, "2026-08.json"), encoding="utf-8").read()
    assert HF_TOKEN not in raw
    assert json.loads(raw)[0]["url"] == "https://github.com/foo/bar"


def test_candidates_log_has_no_secret(tmp_path):
    """candidates 로그의 title·description도 같은 경로로 커밋된다."""
    base = str(tmp_path / "candidates")
    now = datetime(2026, 8, 12, 1, 2, tzinfo=KST)
    cands = redact_articles([{
        "url": "https://example.com/leak",
        "title": f"유출된 키 {SAMPLES['aws_key_id']}",
        "description": f"본문에 {SAMPLES['openai']} 가 그대로 있었다",
        "source": "hackernews",
    }])
    candidates.log(cands, set(), now, base_dir=base)

    raw = open(os.path.join(base, "2026-08.json"), encoding="utf-8").read()
    assert SAMPLES["aws_key_id"] not in raw
    assert SAMPLES["openai"] not in raw
    assert "유출된 키" in raw                      # 기사 자체는 차단하지 않는다


def test_pipeline_wiring():
    """build.py의 삽입 지점이 유지되는지 — 순서가 어긋나면 마스킹이 새어나간다."""
    src = open(os.path.join(ROOT, "build.py"), encoding="utf-8").read()
    assert src.count("redact_articles(") == 3

    collect = src.index('redact_articles(articles, "수집")')
    body = src.index('redact_articles(enrich(picked), "본문")')
    summary = src.index('redact_articles(picked, "요약")')

    assert collect < src.index("candidates.log(")      # 후보 로그 전에 마스킹
    assert body < src.index("summarize_all(")          # LLM 전송 전에 마스킹
    assert summary < src.index("archive.append(")      # 아카이브 기록 전에 마스킹
