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


def _workflow() -> str:
    path = os.path.join(ROOT, ".github", "workflows", "daily.yml")
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_취소로_끝나도_알림이_간다():
    """timeout-minutes를 넘기면 job은 cancelled로 끝난다. failure()는 cancelled에서
    거짓이라, 조건이 failure()만이면 커밋도 이슈도 없이 사이트만 조용히 낡는다."""
    wf = _workflow()
    assert "timeout-minutes:" in wf, "타임아웃이 없다면 이 테스트의 전제가 바뀐 것이다"
    assert "if: failure() || cancelled()" in wf


def test_푸시_전에_원격_데이터를_합친다():
    """`-X theirs`는 '방금 만든 파일이 이긴다'는 뜻이다. 원격이 앞서 있으면 그
    사이 쌓인 기사와 seen 기록이 조용히 사라진다. 먼저 합집합으로 만들어
    상위집합이 된 뒤에야 이겨도 안전하다."""
    wf = _workflow()
    assert "merge_remote_data.py" in wf
    merge = wf.index("merge_remote_data.py")
    rebase = wf.index("git pull --rebase")
    assert merge < rebase, "병합이 rebase보다 먼저 와야 한다"
    assert "git fetch origin main" in wf


def test_병합_스크립트가_있고_읽힌다():
    path = os.path.join(ROOT, "scripts", "merge_remote_data.py")
    assert os.path.exists(path)
    src = open(path, encoding="utf-8").read()
    # 더하기만 하는 자료 두 가지를 모두 다뤄야 한다
    assert "data/seen.json" in src
    assert "docs/data/articles" in src


def test_병합이_있던_항목을_건드리지_않는다(tmp_path):
    """복구 스크립트의 제1원칙. 원격을 뼈대로 다시 쓰면 줄 수는 덜 바뀌지만
    같은 기사의 다른 판본으로 교체되면서 upvotes·출처가 조용히 달라진다."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "mrd", os.path.join(ROOT, "scripts", "merge_remote_data.py"))
    mrd = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mrd)

    local = [{"url": "https://a/1", "batch": "2026-09-03", "upvotes": 87},
             {"url": "https://a/3", "batch": "2026-09-01", "upvotes": 5}]
    missing = [{"url": "https://a/2", "batch": "2026-09-02", "upvotes": 0}]
    out = mrd._insert_by_batch(local, missing)

    assert [x["url"] for x in out] == ["https://a/1", "https://a/2", "https://a/3"]
    assert out[0] == local[0] and out[2] == local[1], "있던 항목이 바뀌었다"


def test_병합이_정본과_같은_형식으로_쓴다():
    """형식이 다르면 몇 건 되살리는 데 파일 전체가 새 덩어리로 쌓인다."""
    src = open(os.path.join(ROOT, "scripts", "merge_remote_data.py"),
               encoding="utf-8").read()
    assert "indent=1" in src, "archive·seen은 indent=1이다"
    assert "sort_keys=sort_keys" in src, "seen은 키 정렬까지 맞춰야 한다"
    assert "normalize_url" in src, "같은 기사 판정은 한 규칙으로 해야 한다"


def test_예비_cron_은_주_실행보다_뒤다():
    """예약이 정각의 수동 실행보다 앞서 오면 guard 창에 아직 아무것도 없어
    둘 다 돈다. 주 실행이 정각이므로 cron 은 그 뒤여야 한다."""
    import yaml
    d = yaml.safe_load(open(os.path.join(ROOT, ".github", "workflows", "daily.yml"), encoding="utf-8"))
    on = d.get(True) or d.get("on")
    cron = on["schedule"][0]["cron"]
    minute, hours = cron.split()[0], cron.split()[1]
    assert minute == "55" and hours == "7,15,23", cron   # 정각(UTC 7·15·23) + 55분


def test_guard_는_성공과_진행중만_인정한다():
    """failure 만 빼는 식이면 timed_out 을 성공으로 세어 예비가 안 돈다."""
    src = open(os.path.join(ROOT, ".github", "workflows", "daily.yml"), encoding="utf-8").read()
    assert 'conclusion == \\"success\\" or .conclusion == \\"\\"' in src
    assert "8 hours ago" in src


def test_guard_는_수동_실행에서_러너를_띄우지_않는다():
    import yaml
    d = yaml.safe_load(open(os.path.join(ROOT, ".github", "workflows", "daily.yml"), encoding="utf-8"))
    assert d["jobs"]["guard"]["if"] == "github.event_name == 'schedule'"
    assert "!cancelled()" in d["jobs"]["build"]["if"]
