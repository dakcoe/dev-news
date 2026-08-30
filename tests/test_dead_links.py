"""죽은 링크 게재 차단 (block-dead-links).

재현하는 결함: enrich가 `raise_for_status()`로 404와 일시적 오류를 똑같이
삼켜 상태 코드가 파이프라인 밖으로 나오지 않았다. 그래서 이미 사라진 링크가
그대로 실렸다 — 최신 250건 실측에서 3건(hada.io 404, dev.to 404, web.archive 503).

오탐 방지가 설계의 핵심이다. 실측 403 4건(economist·stanford·oup·axios)은
전부 살아 있는 페이지이고 봇 차단일 뿐이라 빼면 안 된다.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from build import drop_dead_links  # noqa: E402


def _art(status, url="https://e.com/x"):
    a = {"url": url, "title": "t", "source": "hackernews"}
    if status is not None:
        a["link_status"] = status
    return a


def test_drops_dead():
    kept, dropped = drop_dead_links([_art("dead", "https://e.com/1"),
                                     _art("ok", "https://e.com/2")])
    assert [a["url"] for a in kept] == ["https://e.com/2"]
    assert [a["url"] for a in dropped] == ["https://e.com/1"]


def test_keeps_unknown():
    """5xx·타임아웃은 일시 장애일 수 있다 — 빼지 않는다."""
    kept, dropped = drop_dead_links([_art("unknown")])
    assert len(kept) == 1 and not dropped


def test_keeps_articles_without_status():
    """판정이 없으면 남긴다 — enrich가 건너뛴 경로도 있다."""
    kept, dropped = drop_dead_links([_art(None)])
    assert len(kept) == 1 and not dropped


def test_empty_input():
    assert drop_dead_links([]) == ([], [])


# ------------------------------------------------- 판정표 (api_health 재사용)
def test_classify_table_matches_requirements():
    from news.api_health import classify
    assert classify(404, None) == "dead"
    assert classify(410, None) == "dead"
    assert classify(None, "dns") == "dead"
    assert classify(None, "refused") == "dead"
    # 살아 있다 — 봇 차단·요청 과다·인증 요구
    for code in (200, 301, 401, 403, 429):
        assert classify(code, None) == "ok", f"{code}는 살아있음이어야 한다"
    # 모르겠다 — 일시 장애·타임아웃
    assert classify(503, None) == "unknown"
    assert classify(500, None) == "unknown"
    assert classify(None, "timeout") == "unknown"
