"""미리 받기의 상태 전이는 문자열만 검사하면 누락된 분기를 잡지 못한다."""
import json
from pathlib import Path
import subprocess

import pytest
import yaml

from news.render import render

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def prewarm_page(tmp_path_factory):
    shard = sorted((ROOT / "docs/data/articles").glob("*.json"))[-1]
    articles = json.loads(shard.read_text(encoding="utf-8"))[:3]
    page = tmp_path_factory.mktemp("prewarm") / "index.html"
    about = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))["about"]
    render(articles, str(page), about=about)
    return page


@pytest.mark.parametrize("kind", ["apis", "skills"])
@pytest.mark.parametrize("case", [
    "pending_success", "pending_failure", "failure_then_click",
    "ordinary_failure", "hidden_success", "malformed_json",
])
def test_prewarm_loading(prewarm_page, kind, case):
    run_case(prewarm_page, kind, case)


@pytest.mark.parametrize("case", [
    "idle", "fallback", "revisit", "save_data", "2g", "slow-2g", "3g", "unknown",
    "tab_before_idle", "loaded_before_idle", "failed_before_idle",
])
def test_prewarm_scheduling(prewarm_page, case):
    run_case(prewarm_page, "schedule", case)


def run_case(page, kind, case):
    result = subprocess.run(
        ["node", str(ROOT / "tests/js/prewarm_execution.mjs"), str(page), kind, case],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
