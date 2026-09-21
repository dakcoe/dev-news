"""문자열 존재 검사로 놓친 필터 조건을 실제 기사와 실행 결과로 지킨다.

unified-filter-panel: 옛 패널 배치가 아니라 현재 필터 의미를 검증한다.
"""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from news.render import render


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tests/js/filter_execution.mjs"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")


@pytest.fixture(scope="module")
def filter_page(tmp_path_factory):
    articles = []
    for shard in sorted((ROOT / "docs/data/articles").glob("*.json")):
        articles.extend(json.loads(shard.read_text(encoding="utf-8")))
    assert articles, "실제 기사 코퍼스가 필요하다"
    page = tmp_path_factory.mktemp("filters") / "index.html"
    render(articles, str(page))
    return page


@pytest.mark.parametrize("case", ["filters", "sort", "controls", "archive"])
def test_filter_execution(filter_page, case):
    result = subprocess.run(
        ["node", str(RUNNER), str(filter_page), str(ROOT / "docs/data"), case],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["case"] == case
