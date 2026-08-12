"""실패·열화 알림 회귀 테스트 (add-failure-alert).

배경: 2026-08-12 01:02 KST 회차가 push 거부로 죽었는데 하루 뒤에 사람이 눈으로
발견했다. 더 큰 사각지대는 `if: failure()`가 못 잡는 경로다 — 새 기사 없음,
요약 한도로 일부만 게시(SPEC 1.6), 변경 없어 커밋 생략은 전부 exit 0이다.
"""
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from build import emit_actions_output  # noqa: E402

WORKFLOW = os.path.join(ROOT, ".github", "workflows", "daily.yml")
NOTIFY = os.path.join(ROOT, "scripts", "notify.sh")


def _wf():
    with open(WORKFLOW, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _steps():
    return _wf()["jobs"]["build"]["steps"]


# ------------------------------------------------------- 열화 판정
def test_degraded_when_below_threshold(tmp_path, monkeypatch):
    out = tmp_path / "gh_out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    assert emit_actions_output(3, 10) is True
    body = out.read_text(encoding="utf-8")
    assert "published=3" in body and "degraded=true" in body


def test_not_degraded_at_threshold(tmp_path, monkeypatch):
    out = tmp_path / "gh_out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    assert emit_actions_output(10, 10) is False
    assert "degraded=false" in out.read_text(encoding="utf-8")


def test_zero_published_is_degraded(tmp_path, monkeypatch):
    """새 기사가 없어 조기 반환하는 경로도 신호를 낸다."""
    out = tmp_path / "gh_out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    assert emit_actions_output(0, 10) is True


def test_threshold_zero_never_degrades(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "gh_out"))
    assert emit_actions_output(0, 0) is False


def test_local_run_writes_nothing(monkeypatch, capsys):
    """GITHUB_OUTPUT이 없는 로컬 실행에서 터지지 않는다."""
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    assert emit_actions_output(1, 10) is True     # 판정은 하되 파일은 안 건드린다
    assert "열화" in capsys.readouterr().out


def test_appends_not_overwrites(tmp_path, monkeypatch):
    """$GITHUB_OUTPUT은 여러 스텝이 공유하므로 append여야 한다."""
    out = tmp_path / "gh_out"
    out.write_text("preexisting=1\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    emit_actions_output(12, 10)
    assert "preexisting=1" in out.read_text(encoding="utf-8")


# ------------------------------------------------------- 워크플로 배선
def test_issues_write_permission():
    """없으면 gh가 403으로 조용히 실패해 알림이 안 간다."""
    assert _wf()["permissions"]["issues"] == "write"


def test_failure_step_exists():
    step = next(s for s in _steps() if s.get("name") == "실패 알림")
    assert step["if"] == "failure()"
    assert "scripts/notify.sh" in step["run"]


def test_degraded_step_gated_on_build_output():
    step = next(s for s in _steps() if s.get("name") == "열화 알림")
    assert "steps.build.outputs.degraded == 'true'" in step["if"]
    assert "success()" in step["if"]      # 실패 회차에 두 번 알리지 않는다


def test_build_step_has_id():
    """id가 없으면 steps.build.outputs를 참조할 수 없다."""
    step = next(s for s in _steps() if s.get("name") == "수집 · 요약 · 페이지 생성")
    assert step["id"] == "build"


def test_alert_steps_run_after_commit():
    names = [s.get("name") for s in _steps()]
    assert names.index("변경분 커밋") < names.index("실패 알림")


def test_config_has_threshold():
    cfg = yaml.safe_load(open(os.path.join(ROOT, "config.yaml"), encoding="utf-8"))
    assert cfg["alert"]["min_published"] > 0


# ------------------------------------------------------- 중복 방지
def test_notify_script_dedupes_by_title():
    """매번 새로 만들면 연속 실패에 이슈가 쌓여서 그것도 묻힌다."""
    src = open(NOTIFY, encoding="utf-8").read()
    assert "gh issue list --state open" in src
    assert "select(.title == env.TITLE)" in src   # 따옴표 섞인 제목도 안전
    assert "gh issue comment" in src and "gh issue create" in src
    assert "set -euo pipefail" in src
