"""build.py 단계 연결 — 요약·제외·보충·seen 기록이 실제로 맞물리는지 돌려서 본다.

함수 하나하나는 각자의 테스트가 있지만, 그 함수들을 잇는 build.py 는 그동안
문자열이 들어 있는지만 확인했다. 2026-10-07 리뷰에서 build.py 에 버그 6개
(요약 실패분 게재, seen 범위 축소, 게재 기준 제거, 대기 0초 등)를 넣어 봤더니
734건이 전부 통과했다. 여기서는 네트워크·LLM·임베딩만 가짜로 바꾸고 나머지는
실제 코드(pick, 마스킹, 무관 선언 필터, prepare_published, main)를 그대로 태운다.
"""
import sys

import pytest

import build
from news import summarizer
from news.core import discussion, similar

TOKEN = "ghp_" + "r" * 36          # tests/test_redact.py 와 같은 GitHub 토큰 형태
SELF_IRRELEVANT_WHY = "백엔드 개발자의 업무와 무관한 영화 이야기다."


def _art(url, source="hackernews", score=1.0, body="본문"):
    return {"url": url, "title": url, "source": source, "score": score, "content": body}


class FakeSummarizer:
    """제목의 표시로 결과를 정한다. FAIL=요약 실패, SELF=무관 선언, IRR=분류 무관.

    실제 summarize_all 처럼 순서대로 부르고, max_calls·stop_after 를 지키고,
    stats 에 호출 수를 적는다. 받은 본문을 기록해 마스킹이 앞에 있는지 본다.
    """

    def __init__(self):
        self.order, self.bodies, self.calls_per_run = [], [], []

    def __call__(self, articles, max_calls=50, stop_after=None, stats=None, **_):
        out, calls = [], 0
        for i, a in enumerate(articles):
            if calls >= max_calls:
                out.append({**a, "llm_done": False})
                continue
            calls += 1
            self.order.append(a["url"])
            self.bodies.append(a.get("content", ""))
            if "FAIL" in a["url"]:
                out.append({**a, "llm_done": False})
            else:
                why = SELF_IRRELEVANT_WHY if "SELF" in a["url"] else "쓸모 있다."
                # 모델이 본문의 토큰을 요약에 되뱉는 경우
                out.append({**a, "summary": f"요약 {a.get('content', '')}", "why": why,
                            "relevance": summarizer.IRRELEVANT if "IRR" in a["url"] else "게재",
                            "llm_done": True})
            if stop_after is not None:
                ok = sum(1 for x in out if x.get("llm_done"))
                if ok >= stop_after:
                    out.extend({**x, "llm_done": False} for x in articles[i + 1:])
                    break
        if stats is not None:
            stats["calls"] = calls
        self.calls_per_run.append(calls)
        return out


@pytest.fixture
def fake(monkeypatch):
    s = FakeSummarizer()
    monkeypatch.setattr(summarizer, "summarize_all", s)
    monkeypatch.setattr(build, "enrich", lambda arts: arts)
    monkeypatch.setattr(discussion, "fill_from_discussion", lambda arts: arts)
    monkeypatch.setattr(build, "drop_dead_links",
                        lambda arts: ([a for a in arts if "DEAD" not in a["url"]],
                                      [a for a in arts if "DEAD" in a["url"]]))
    monkeypatch.setattr(build.archive, "load_all", lambda: [])
    # 같은 사건: 주소에 DUP 이 든 기사를 앞선 기사와 같은 사건으로 본다
    monkeypatch.setattr(similar, "drop_same_story",
                        lambda new, recent: ([a for a in new if "DUP" not in a["url"]],
                                             [a for a in new if "DUP" in a["url"]]))
    return s


def _cfg(top_n=4, gate=True, overpick=3, quota=None, max_calls=50):
    return {"scraper": {"top_n": top_n, "relevance_gate": gate, "overpick": overpick,
                        "per_source": 10},
            "source_quota": quota if quota is not None else {"github": 1},
            "llm": {"max_calls_per_run": max_calls, "pause_seconds": 0}}


def _urls(arts):
    return [a["url"] for a in arts]


def test_뺀_자리는_예비에서_요약해_채운다(fake):
    # 점수순. github 는 점수가 낮아 맨 뒤지만 예약석 1칸이 있다
    picked = [_art("h1", score=9), _art("h2-DUP", score=8), _art("h3-SELF", score=7),
              _art("h4", score=6), _art("h5", score=5), _art("h6", score=4),
              _art("g1", "github", 1), _art("g2", "github", 0.5)]
    published, removed, dead = build.prepare_published(picked, _cfg(), no_ai=False)

    assert sorted(_urls(published)) == ["g1", "h1", "h4", "h5"]
    assert sorted(_urls(removed)) == ["h2-DUP", "h3-SELF"]
    # 본선(예약석 포함 4건)을 먼저 요약하고, 모자란 2건만 예비에서 더 부른다
    assert set(fake.order[:4]) == {"h1", "h2-DUP", "h3-SELF", "g1"}
    assert fake.order[4:] == ["h4", "h5"]


def test_게재_기준이_무관으로_분류한_기사를_뺀다(fake):
    picked = [_art("h1-IRR", score=9), _art("h2", score=8), _art("h3", score=7)]
    published, removed, _ = build.prepare_published(picked, _cfg(top_n=2, quota={}),
                                                    no_ai=False)
    assert _urls(published) == ["h2", "h3"] and _urls(removed) == ["h1-IRR"]


def test_github_예약석은_점수가_낮아도_요약된다(fake):
    picked = [_art(f"h{i}", score=10 - i) for i in range(6)] + [_art("g1", "github", 0.1)]
    published, _, _ = build.prepare_published(picked, _cfg(), no_ai=False)
    assert "g1" in _urls(published)
    assert len(published) == 4


def test_요약_실패분은_게재도_제외도_아니다(fake):
    # 제외(seen 등록)로 가면 다음 회차 재시도가 끊긴다 (SPEC 1.6)
    picked = [_art("h1-FAIL", score=9), _art("h2", score=8), _art("h3", score=7)]
    published, removed, _ = build.prepare_published(picked, _cfg(top_n=2, quota={}),
                                                    no_ai=False)
    assert _urls(published) == ["h2", "h3"]
    assert removed == []


def test_보충도_호출_예산을_이어_쓴다(fake):
    picked = [_art("h1-DUP", score=9), _art("h2-DUP", score=8), _art("h3", score=7),
              _art("h4", score=6), _art("h5", score=5)]
    build.prepare_published(picked, _cfg(top_n=2, quota={}, max_calls=3), no_ai=False)
    # 본선 2회 + 보충 1회 — 보충이 예산을 새로 받으면 3회를 넘긴다
    assert sum(fake.calls_per_run) == 3


def test_게재_기준이_꺼져_있으면_보충하지_않는다(fake):
    picked = [_art("h1-DUP", score=9), _art("h2", score=8)]
    published, removed, _ = build.prepare_published(picked, _cfg(gate=False, quota={}),
                                                    no_ai=False)
    assert _urls(published) == ["h2"] and _urls(removed) == ["h1-DUP"]
    assert len(fake.calls_per_run) == 1


def test_LLM_에는_마스킹된_본문만_가고_요약도_마스킹된다(fake):
    picked = [_art("h1", body=f"키 유출 {TOKEN} 사건")]
    published, _, _ = build.prepare_published(picked, _cfg(top_n=1, quota={}), no_ai=False)
    assert TOKEN not in fake.bodies[0]
    assert TOKEN not in published[0]["summary"]


def test_보호_출처는_무관_선언이어도_남는다(fake):
    # 교차 출처 2곳 이상이면 보호 목록 — 무관 선언 필터도 건드리지 않는다
    a = {**_art("h1-SELF", score=9), "cross_source_count": 2}
    published, removed, _ = build.prepare_published([a], _cfg(top_n=1, quota={}), no_ai=False)
    assert _urls(published) == ["h1-SELF"] and removed == []


def test_요약_없이_돌리면_같은_사건_판정을_부르지_않는다(fake, monkeypatch):
    def boom(*_):
        raise AssertionError("--no-ai 에서 같은 사건 판정(Groq·임베딩)을 불렀다")
    monkeypatch.setattr(similar, "drop_same_story", boom)
    published, _, _ = build.prepare_published([_art("h1")], _cfg(top_n=1, quota={}), no_ai=True)
    assert _urls(published) == ["h1"]


def test_main_은_게재·제외·죽은_링크를_seen_에_넣고_요약_실패분은_뺀다(fake, monkeypatch):
    picked = [_art("h1", score=9), _art("h2-DUP", score=8), _art("h3-DEAD", score=7),
              _art("h4-FAIL", score=6)]
    monkeypatch.setattr(build, "load_dotenv", lambda: None)
    monkeypatch.setattr(build, "load_config", lambda: _cfg(top_n=4, quota={}))
    monkeypatch.setattr(build.archive, "migrate_legacy", lambda: None)
    monkeypatch.setattr(build, "collect_candidates", lambda cfg, when: (picked, []))
    monkeypatch.setattr(build, "select_articles", lambda arts, cfg, now, today: arts)
    written, seen = [], []
    monkeypatch.setattr(build, "write_outputs", lambda pub, cfg, now, out: written.extend(pub))
    monkeypatch.setattr(build.seen_db, "mark_seen", lambda arts: seen.extend(arts))
    monkeypatch.setattr(build, "emit_actions_output", lambda *a: None)
    monkeypatch.setattr(sys, "argv", ["build.py"])

    assert build.main() == 0
    assert _urls(written) == ["h1"]
    assert sorted(_urls(seen)) == ["h1", "h2-DUP", "h3-DEAD"]
