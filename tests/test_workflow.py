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


def test_수집_워크플로는_수동_실행_전용이다():
    """수집은 바깥 기계가 scripts/publish.sh 로 돌린다. 러너 IP 가 막혀 본문
    추출이 8% 실패했고 예약은 2~5시간 늦었다. 여기 cron 이 다시 생기면 회차가
    두 배가 된다."""
    import yaml
    d = yaml.safe_load(open(os.path.join(ROOT, ".github", "workflows", "daily.yml"), encoding="utf-8"))
    on = d.get(True) or d.get("on")
    assert list(on.keys()) == ["workflow_dispatch"], on
    assert "guard" not in d["jobs"]


def test_감시_워크플로는_키_없이_돈다():
    """수집 기계가 죽은 것을 알 길이 이것뿐이다. 시크릿을 쓰면 안 된다 — 감시가
    수집으로 변질되는 것을 막는다."""
    import yaml
    p = os.path.join(ROOT, ".github", "workflows", "watchdog.yml")
    src = open(p, encoding="utf-8").read()
    d = yaml.safe_load(src)
    on = d.get(True) or d.get("on")
    assert "schedule" in on
    assert "secrets." not in src
    assert "notify.sh" in src and "36000" in src   # 10시간


def test_로컬_실행_스크립트가_알림_세_가지를_그대로_낸다():
    src = open(os.path.join(ROOT, "scripts", "publish.sh"), encoding="utf-8").read()
    for t in ("🔴 뉴스 수집 실패", "🟡 게시 건수 급감", "🟡 출처 침묵"):
        assert t in src, t
    assert "merge_remote_data.py origin/main" in src
    assert "pull --rebase -X theirs" in src
    assert 'git add -A docs data' in src


def test_로컬_실행_스크립트가_후원_링크를_감시한다():
    """외부 송금 링크는 예고 없이 끝날 수 있다. 회차마다 찔러 보고 200 이 아니면
    이슈를 연다."""
    src = open(os.path.join(ROOT, "scripts", "publish.sh"), encoding="utf-8").read()
    assert "🟡 후원 링크 응답 이상" in src
    assert 'about") or {}).get("coffee")' in src
