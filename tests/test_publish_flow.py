"""scripts/publish.sh 를 실제로 돌려 본다 — 임시 원격 저장소, 가짜 build.py, 가짜 알림.

그동안 publish.sh 테스트는 파일에 특정 문자열이 있는지만 봤다. 여기서는 셸
스크립트를 그대로 실행해 push 거부·알림 실패·회차 잠금이 실제로 어떻게 끝나는지
확인한다. 네트워크와 gh 는 쓰지 않는다.
"""
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FAKE_BUILD = """#!/usr/bin/env bash
# build.py 대신: 기사 파일 하나를 바꾸고 결과를 GITHUB_OUTPUT 에 적는다
mkdir -p docs data
date +%s%N > docs/stamp.txt
echo "published=20" >> "$GITHUB_OUTPUT"
"""

FAKE_NOTIFY = """#!/usr/bin/env bash
echo "$1|$2" >> "$NOTIFY_LOG"
[ -z "$NOTIFY_FAIL" ]
"""


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    if not shutil.which("git"):
        pytest.skip("git 없음")
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    subprocess.run(["git", "clone", "-q", str(remote), str(work)], check=True)
    _git(work, "config", "user.email", "t@t")
    _git(work, "config", "user.name", "t")
    (work / "scripts").mkdir()
    shutil.copy(os.path.join(ROOT, "scripts", "publish.sh"), work / "scripts" / "publish.sh")
    (work / "scripts" / "notify.sh").write_text(FAKE_NOTIFY)
    # publish.sh 는 원격 병합 단계에서만 이 스크립트를 부른다
    (work / "scripts" / "merge_remote_data.py").write_text("")
    (work / "venv" / "bin").mkdir(parents=True)
    py = work / "venv" / "bin" / "python"
    # "$PY build.py" 로 불리므로 첫 인자를 무시하고 가짜 빌드를 돈다
    py.write_text("#!/usr/bin/env bash\nbash \"$(dirname \"$0\")/../../fake_build.sh\"\n")
    py.chmod(0o755)
    (work / "fake_build.sh").write_text(FAKE_BUILD)
    (work / ".gitignore").write_text("logs/\nvenv/\nfake_build.sh\n")
    (work / "docs").mkdir()
    (work / "docs" / "stamp.txt").write_text("0\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "init")
    _git(work, "push", "-q", "origin", "main")
    return {"remote": remote, "work": work, "tmp": tmp_path}


def _run(repo, **env):
    e = {**os.environ, "NOTIFY_LOG": str(repo["tmp"] / "notify.log"),
         "DEV_NEWS_LOCK": str(repo["tmp"] / "publish.lock"), **env}
    e.pop("GITHUB_OUTPUT", None)
    return subprocess.run(["bash", "scripts/publish.sh"], cwd=repo["work"], env=e,
                          capture_output=True, text=True)


def _log(repo):
    return (repo["work"] / "logs" / "publish.log").read_text()


def _alerts(repo):
    p = repo["tmp"] / "notify.log"
    return p.read_text() if p.exists() else ""


def test_정상_회차는_푸시하고_잠금을_푼다(repo):
    assert _run(repo).returncode == 0
    assert "push 완료" in _log(repo)
    remote_head = _git(repo["remote"], "log", "-1", "--format=%s").stdout.strip()
    assert remote_head.startswith("뉴스 갱신")
    assert not (repo["tmp"] / "publish.lock").exists()


def test_push_가_거부되면_커밋을_브랜치에_두고_원격으로_되돌린다(repo):
    hook = repo["remote"] / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho 'GH013: secret detected' >&2\nexit 1\n")
    hook.chmod(0o755)
    assert _run(repo).returncode == 1

    work = repo["work"]
    branches = _git(work, "branch", "--list", "push-failed/*").stdout
    assert "push-failed/" in branches
    # 로컬 main 이 원격과 같아야 다음 회차가 거부된 커밋 위에 쌓이지 않는다
    assert (_git(work, "rev-parse", "HEAD").stdout
            == _git(work, "rev-parse", "origin/main").stdout)
    assert "push 가 거부됐습니다" in _alerts(repo)

    # 원인이 풀리면 다음 회차는 정상으로 올라간다
    hook.unlink()
    assert _run(repo).returncode == 0


def test_알림이_실패해도_로그에_남는다(repo):
    hook = repo["remote"] / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    _run(repo, NOTIFY_FAIL="1")
    assert "[알림 실패]" in _log(repo)


def test_venv_가_없으면_알린다(repo):
    shutil.rmtree(repo["work"] / "venv")
    assert _run(repo).returncode == 1
    assert "venv 가 없어" in _alerts(repo)


def test_회차가_도는_중이면_rerender_가_멈춘다(tmp_path):
    lock = tmp_path / "publish.lock"
    lock.write_text(str(os.getpid()))          # 살아 있는 프로세스
    work = tmp_path / "w"
    (work / "scripts").mkdir(parents=True)
    shutil.copy(os.path.join(ROOT, "scripts", "rerender.sh"), work / "scripts" / "rerender.sh")
    r = subprocess.run(["bash", "scripts/rerender.sh", "--no-push"], cwd=work,
                       env={**os.environ, "DEV_NEWS_LOCK": str(lock)},
                       capture_output=True, text=True)
    assert r.returncode == 1 and "수집 회차가 도는 중" in r.stdout
