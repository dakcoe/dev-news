"""실제 기사로 생성한 페이지에서 동기화 순서와 로컬 변경 보존을 검증한다."""
import json
from pathlib import Path
import subprocess

import pytest

from news.render import render

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def sync_page(tmp_path_factory):
    shard = sorted((ROOT / "docs/data/articles").glob("*.json"))[-1]
    articles = json.loads(shard.read_text(encoding="utf-8"))[:3]
    page = tmp_path_factory.mktemp("sync") / "index.html"
    render(articles, str(page))
    return page


@pytest.mark.parametrize("case", ["failed_read", "failed_bookmark", "first_union"])
def test_sync_execution(sync_page, case):
    result = subprocess.run(
        ["node", str(ROOT / "tests/js/sync_execution.mjs"), str(sync_page), case],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
