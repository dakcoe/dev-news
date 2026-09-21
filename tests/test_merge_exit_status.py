"""합치지 못했으면 0으로 끝나지 않는다.

scripts/publish.sh 는 이 종료 코드를 보고 멈춘다. 바로 다음 줄이
`git pull --rebase -X theirs` 이고, 그 rebase 는 충돌을 전부 우리 쪽으로
밀어서 원격에만 있던 기사와 seen 기록을 지운다. 합집합을 만들지 못한 채
거기까지 가면 안 된다.
"""
import importlib
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

mrd = importlib.import_module("merge_remote_data")


def _fresh():
    mrd.FAILED.clear()
    return mrd


def test_합칠_것이_없으면_0이다(monkeypatch):
    m = _fresh()
    monkeypatch.setattr(m, "merge_seen", lambda: 0)
    monkeypatch.setattr(m, "merge_shards", lambda: 0)
    assert m.main() == 0


def test_못_읽은_파일이_있으면_0이_아니다(monkeypatch):
    m = _fresh()
    monkeypatch.setattr(m, "merge_seen", lambda: (m.FAILED.append("data/seen.json"), 0)[1])
    monkeypatch.setattr(m, "merge_shards", lambda: 0)
    assert m.main() == 1


def test_원격본이_깨졌으면_실패로_남긴다(monkeypatch):
    """그 파일이 그 ref 에 없는 것(새로 생긴 파일)과는 다르다."""
    m = _fresh()

    class R:
        stdout = b"{not json"

    monkeypatch.setattr(m.subprocess, "run", lambda *a, **k: R())
    assert m.remote_json("data/seen.json") is None
    assert m.FAILED == ["data/seen.json"]

    m.FAILED.clear()
    def boom(*a, **k):
        raise subprocess.CalledProcessError(128, "git")
    monkeypatch.setattr(m.subprocess, "run", boom)
    assert m.remote_json("data/새파일.json") is None
    assert m.FAILED == []          # 없는 파일은 실패가 아니다


def test_형태가_다르면_실패로_남긴다(monkeypatch):
    m = _fresh()
    monkeypatch.setattr(m, "remote_json", lambda p: {"a": "1"})
    monkeypatch.setattr(m, "local_json", lambda p: ["a"])
    assert m.merge_seen() == 0
    assert m.FAILED == ["data/seen.json"]


def test_publish_sh_가_종료코드를_본다():
    """스크립트가 실패를 알려도 부르는 쪽이 안 보면 소용이 없다."""
    sh = open(os.path.join(ROOT, "scripts", "publish.sh"), encoding="utf-8").read()
    assert 'if ! "$PY" scripts/merge_remote_data.py origin/main; then' in sh
    # 주석에도 스크립트 이름이 나온다. 가드 문장 뒤부터 본다.
    guard = sh.split('if ! "$PY" scripts/merge_remote_data.py origin/main; then')[1]
    assert "exit 1" in guard.split("\n    fi")[0]
