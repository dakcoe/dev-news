"""본문 수집 실패 기록 (record-fetch-failures).

동기: 실패가 print로만 나가고 사라져서, 이번 세션에 원인을 분류하려고 최근
250건 URL에 요청을 다시 날리는 재현 스크립트를 짜야 했다. 그 결과(403 4건 ·
404 3건 · SPA 4건 · 짧은 본문 4건)가 이후 작업 세 개의 근거가 됐다.
기록만 있었으면 조회 한 번이면 될 일이었다.
"""
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from news.core.fetch_health import MAX_RUNS, load, reason_of, record  # noqa: E402


# ------------------------------------------------------------------ 사유 분류
def test_reason_distinguishes_blocked_from_ok():
    """게재 판단에는 403도 ok지만 진단할 때는 구분돼야 한다."""
    assert reason_of(status="ok", code=200, content="본문" * 100) == "ok"
    assert reason_of(status="ok", code=403, content=None) == "blocked"
    assert reason_of(status="ok", code=429, content=None) == "blocked"


def test_reason_dead_and_unavailable():
    assert reason_of(status="dead", code=404, content=None) == "dead"
    assert reason_of(status="dead", code=None, content=None) == "dead"
    assert reason_of(status="unknown", code=503, content=None) == "unavailable"


def test_reason_empty_vs_short():
    assert reason_of(status="ok", code=200, content=None) == "empty"
    assert reason_of(status="ok", code=200, content="짧음", accepted=False) == "short"


def test_reason_github_exempt():
    assert reason_of(status=None, code=None, content="README") == "github"


# ------------------------------------------------------------------ 기록
def _rows():
    return [{"url": "https://e.com/1", "source": "hackernews", "reason": "blocked"},
            {"url": "https://e.com/2", "source": "devto", "reason": "ok"}]


def test_record_writes_summary_and_failures(tmp_path):
    path = str(tmp_path / "fetch_health.json")
    record(_rows(), path=path)
    data = load(path)
    run = data["runs"][-1]
    assert run["counts"] == {"blocked": 1, "ok": 1}
    assert [f["url"] for f in run["failures"]] == ["https://e.com/1"], "ok는 실패가 아니다"
    assert run["at"]


def test_runs_are_capped(tmp_path):
    path = str(tmp_path / "fetch_health.json")
    for _ in range(MAX_RUNS + 5):
        record(_rows(), path=path)
    assert len(load(path)["runs"]) == MAX_RUNS


def test_corrupt_file_is_recovered(tmp_path):
    path = str(tmp_path / "fetch_health.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write("{ this is not json")
    record(_rows(), path=path)
    assert len(load(path)["runs"]) == 1


def test_write_failure_does_not_raise(tmp_path):
    """기록은 부가 기능이다 — 실패해도 회차를 죽이지 않는다."""
    bad = str(tmp_path / "nope" / "deeper" / "x.json")
    os.makedirs(os.path.dirname(bad), exist_ok=True)
    os.chmod(os.path.dirname(bad), 0o500)
    try:
        record(_rows(), path=bad)      # 예외가 나가지 않기만 하면 된다
    finally:
        os.chmod(os.path.dirname(bad), 0o700)


def test_load_missing_file():
    assert load("/nonexistent/path/x.json") == {"runs": []}


def test_empty_rows(tmp_path):
    path = str(tmp_path / "fetch_health.json")
    record([], path=path)
    assert load(path)["runs"][-1]["counts"] == {}
