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
