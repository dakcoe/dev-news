"""출처 침묵 감지 (add-source-silence-alert).

배경: Trendshift·GitHub 트렌딩은 HTML 파싱이라 화면이 바뀌면 조용히 0건이 된다.
다른 출처가 20건을 채우면 min_published 알림에 안 걸린다.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from news.core.source_health import load, record, silent  # noqa: E402


def _runs(*counts):
    return [{"at": f"t{i}", "counts": c} for i, c in enumerate(counts)]


def test_record_appends_and_trims(tmp_path):
    p = str(tmp_path / "h.json")
    for i in range(5):
        hist = record({"github": i}, f"t{i}", path=p, keep=3)
    assert [h["counts"]["github"] for h in hist] == [2, 3, 4]
    assert load(p) == hist
    assert json.load(open(p, encoding="utf-8")) == hist


def test_load_missing_or_corrupt_is_empty(tmp_path):
    assert load(str(tmp_path / "none.json")) == []
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    assert load(str(p)) == []


def test_silent_after_streak_zero_runs():
    hist = _runs({"github": 5, "trendshift": 0}, {"github": 4, "trendshift": 0},
                 {"github": 6, "trendshift": 0})
    assert silent(hist, streak=3) == ["trendshift"]


def test_one_zero_run_is_not_silent():
    hist = _runs({"trendshift": 25}, {"trendshift": 25}, {"trendshift": 0})
    assert silent(hist, streak=3) == []


def test_recovery_in_the_middle_resets():
    hist = _runs({"trendshift": 0}, {"trendshift": 1}, {"trendshift": 0})
    assert silent(hist, streak=3) == []


def test_not_enough_history():
    assert silent(_runs({"trendshift": 0}, {"trendshift": 0}), streak=3) == []
    assert silent([], streak=3) == []


def test_disabled_source_is_ignored():
    """꺼진 출처는 counts에 없다 — 최근 회차에 빠져 있으면 판정 대상이 아니다."""
    hist = _runs({"reddit": 0, "github": 1}, {"github": 1}, {"github": 1})
    assert silent(hist, streak=3) == []


def test_multiple_silent_sorted():
    hist = _runs({"b": 0, "a": 0, "c": 1}, {"b": 0, "a": 0, "c": 1}, {"b": 0, "a": 0, "c": 0})
    assert silent(hist, streak=3) == ["a", "b"]


def test_피드별로_침묵을_잡는다():
    """합계만 기록하면 피드 하나가 죽어도 rss 총계가 0이 아니라 경고가 영영
    안 뛴다. 실제로 2026-09-13 21:32부터 세 회차 연속 rss가 64건이었다 —
    피드 8개 × 8건이라 두 피드가 죽어 있었는데 아무 신호도 없었다."""
    hist = [{"counts": {"rss:OpenAI": 8, "rss:The Decoder": 0, "hackernews": 60}}
            for _ in range(3)]
    assert silent(hist, streak=3) == ["rss:The Decoder"]


def test_합계만_있으면_못_잡는다():
    """고치기 전 상태를 기록해 둔다 — 같은 상황인데 신호가 없다."""
    hist = [{"counts": {"rss": 64, "hackernews": 60}} for _ in range(3)]
    assert silent(hist, streak=3) == []


def test_rss_수집기가_피드별로_센다():
    import inspect

    from news.scrapers import rss
    sig = inspect.signature(rss.fetch)
    assert "counts" in sig.parameters
    src = inspect.getsource(rss.fetch)
    assert 'f"rss:{name}"' in src


def _h(day, cnt, name="rss:arXiv cs.AI", skip=(5, 6)):
    """2026-09월 어느 날의 회차 한 건. 09-19가 토, 09-20이 일이다."""
    e = {"at": f"2026-09-{day:02d}T08:00:00+09:00", "counts": {name: cnt}}
    if skip:
        e["skip"] = {name: list(skip)}
    return e


def test_휴재_요일은_침묵으로_세지_않는다():
    """feed-skip-days. arXiv는 주말에 <item>이 없는 껍데기를 준다. 그걸 죽음으로 보면 매주
    토·일마다 알람이 뜬다 — 2026-09-19·20에 실제로 그랬다."""
    from news.core.source_health import silent
    # 금·토·일 연속 0건. 주말을 빼면 유효 회차가 금요일 하나뿐이라 아직 판정하지 않는다.
    assert silent([_h(18, 0), _h(19, 0), _h(20, 0)]) == []
    # 정상적으로 받던 출처가 주말에만 0건인 경우도 마찬가지.
    assert silent([_h(17, 8), _h(18, 8), _h(19, 0), _h(20, 0)]) == []


def test_주말을_빼고도_연속_0건이면_알린다():
    """휴재 요일 예외가 진짜 고장까지 덮으면 안 된다."""
    from news.core.source_health import silent
    # 목·금·월이 0건 — 주말을 빼고도 유효 회차 셋이 전부 0이다.
    hist = [_h(17, 0), _h(18, 0), _h(19, 0), _h(20, 0), _h(21, 0)]
    assert silent(hist) == ["rss:arXiv cs.AI"]


def test_휴재_정보가_없으면_예전처럼_판정한다():
    from news.core.source_health import silent
    hist = [_h(d, 0, name="rss:x", skip=None) for d in (22, 23, 24)]
    assert silent(hist) == ["rss:x"]
