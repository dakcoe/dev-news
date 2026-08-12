"""수집 원문(content) 미저장 회귀 테스트 (drop-unused-content).

content는 요약 생성의 입력일 뿐 화면에는 쓰이지 않는다 — template.html이 읽는
필드는 description·image·ko_title·summary·tags·why뿐이다. 그런데도 샤드 용량의
66%(817K자/1.59MB)를 차지했고, data/와 docs/data/에 2벌로 커밋됐으며,
fix-secret-push-block이 막은 토큰 4건이 전부 이 필드 안에 있었다.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from news.core import archive  # noqa: E402
from news.render import to_view_model  # noqa: E402

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 8, 13, 8, 0, tzinfo=KST)

FULL = {
    "url": "https://example.com/a",
    "title": "Example",
    "ko_title": "예시",
    "description": "원문 설명",
    "summary": "두세 문장 요약.",
    "why": "왜 중요한지.",
    "tags": ["ai", "llm"],
    "image": "https://example.com/og.png",
    "source": "hackernews",
    "upvotes": 120,
    "comments": 8,
    "published_at": 1786411329,
    "content": "# README\n\n" + "본문" * 1500,
}


def test_content_not_persisted(tmp_path):
    base = str(tmp_path / "articles")
    archive.append([dict(FULL)], NOW, base_dir=base)
    shard = json.load(open(os.path.join(base, "2026-08.json"), encoding="utf-8"))
    assert "content" not in shard[0]


def test_displayed_fields_survive(tmp_path):
    base = str(tmp_path / "articles")
    archive.append([dict(FULL)], NOW, base_dir=base)
    stored = json.load(open(os.path.join(base, "2026-08.json"), encoding="utf-8"))[0]
    for key in ("url", "title", "ko_title", "description", "summary", "why",
                "tags", "image", "source", "upvotes", "comments", "published_at"):
        assert stored[key] == FULL[key], key
    assert stored["batch"].startswith("2026-08-13")


def test_input_not_mutated(tmp_path):
    """호출자의 dict는 그대로 — 같은 리스트를 뒤에서 또 쓰는 코드가 깨지지 않게."""
    base = str(tmp_path / "articles")
    article = dict(FULL)
    archive.append([article], NOW, base_dir=base)
    assert article["content"] == FULL["content"]


def test_render_unaffected_without_content():
    """content 없이도 뷰 모델이 온전하다 — 화면이 쓰는 건 summary·why다."""
    without = {k: v for k, v in FULL.items() if k != "content"}
    vm = to_view_model([without])[0]
    assert vm["title"] == "예시"
    assert vm["why"] == "왜 중요한지."
    assert "두세 문장" in vm["snip"]
    assert "<p>두세 문장 요약.</p>" == vm["body"]


def test_shipped_shards_have_no_content():
    """일회성 정리가 실제로 반영됐는지 — 커밋된 샤드에 원문이 남아 있으면 실패."""
    for month in archive.months():
        for a in json.load(open(archive._shard_path(month), encoding="utf-8")):
            assert "content" not in a, f"{month}: {a.get('url')}"
