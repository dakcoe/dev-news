"""daily.yml 워크플로우 회귀 테스트.

fix-workflow-push-race: Re-run(옛 스냅샷)이나 동시 push로 원격이 앞서 있어도
수집 결과를 잃지 않도록 push 전에 rebase로 흡수하는 방어 코드가 유지되는지 확인한다.
"""
import os

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "daily.yml")


def _commit_step_script():
    with open(WORKFLOW, encoding="utf-8") as f:
        wf = yaml.safe_load(f)
    steps = wf["jobs"]["build"]["steps"]
    return next(s["run"] for s in steps if s.get("name") == "변경분 커밋")


def test_rebase_before_push():
    script = _commit_step_script()
    assert "git pull --rebase -X theirs origin main" in script
    assert script.index("pull --rebase") < script.index("git push")


def test_checkout_full_history():
    with open(WORKFLOW, encoding="utf-8") as f:
        wf = yaml.safe_load(f)
    checkout = next(s for s in wf["jobs"]["build"]["steps"]
                    if "checkout" in str(s.get("uses", "")))
    assert checkout["with"]["fetch-depth"] == 0
