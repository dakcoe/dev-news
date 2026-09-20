"""누적 파일을 읽기 실패로 잃지 않는다 (news.core.common.load_json).

이 저장소의 누적 파일은 거의 다 같은 모양이다 — 읽어서 오늘 것을 얹고 같은
경로에 다시 쓴다. 읽기 실패가 빈 값으로 돌아오면 그 한 번으로 누적분이
통째로 지워지고, 하루 세 번 도는 파이프라인이 그걸 그대로 커밋·푸시한다.

archive 쪽 같은 사례는 tests/test_archive.py 에 있다.
"""
import json
import os
import sys
from datetime import datetime, timezone

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from news.core.common import DataUnreadable, load_json  # noqa: E402


def test_없는_파일은_기본값이다(tmp_path):
    assert load_json(str(tmp_path / "none.json"), []) == []
    assert load_json(str(tmp_path / "none.json"), {}) == {}


def test_깨진_파일은_예외다(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{망가진", encoding="utf-8")
    with pytest.raises(DataUnreadable):
        load_json(str(p), {})
    assert p.read_text(encoding="utf-8") == "{망가진"      # 원본은 그대로


def test_종류가_다르면_예외다(tmp_path):
    """옛 형식이 남아 있는데 빈 값으로 갈아 끼우면 손실은 똑같다."""
    p = tmp_path / "old.json"
    p.write_text('["예전에는 목록이었다"]', encoding="utf-8")
    with pytest.raises(DataUnreadable):
        load_json(str(p), {})


def test_seen_은_깨진_기록_위에_덮어쓰지_않는다(tmp_path):
    """mark_seen 은 기존 기록에 오늘 것을 얹어 같은 경로에 다시 쓴다. 영구
    보관(SPEC 2.3)이라 한 번 줄면 옛 기사가 전부 미소개로 돌아온다."""
    from news.core import seen

    p = tmp_path / "seen.json"
    seen.mark_seen([{"url": "https://e.com/1"}], str(p))
    p.write_text("{망가진", encoding="utf-8")

    with pytest.raises(DataUnreadable):
        seen.mark_seen([{"url": "https://e.com/2"}], str(p))
    assert p.read_text(encoding="utf-8") == "{망가진"


def test_candidates_는_깨진_샤드_위에_덮어쓰지_않는다(tmp_path):
    """log() 가 그달 판정 로그에 오늘 행을 얹는다. 빈 목록이 되면 그달
    코퍼스가 하루치로 교체되고 스타 Δ 의 근거도 함께 사라진다."""
    from news.core import candidates

    when = datetime(2026, 9, 1, tzinfo=timezone.utc)
    candidates.log([{"url": "https://e.com/1", "title": "t"}], set(), when, None, str(tmp_path))
    shard = tmp_path / "2026-09.json"
    assert json.loads(shard.read_text(encoding="utf-8"))

    shard.write_text("[망가진", encoding="utf-8")
    with pytest.raises(DataUnreadable):
        candidates.log([{"url": "https://e.com/2", "title": "t"}], set(), when, None, str(tmp_path))
    assert shard.read_text(encoding="utf-8") == "[망가진"


def test_카탈로그는_못_읽으면_기존_파일을_남긴다(tmp_path):
    """apis·skills 의 sync() 는 예외를 받아 기존 파일을 그대로 둔다. 읽기
    실패를 빈 값으로 삼키면 apis 는 MIN_RATIO 방어선이 꺼지고, skills 는
    200건 전부 새 진입으로 발행된다."""
    from news import apis_catalog, skills_catalog

    p = tmp_path / "apis.json"
    p.write_text("{망가진", encoding="utf-8")
    with pytest.raises(DataUnreadable):
        apis_catalog._previous_counts(str(p))
    assert apis_catalog.sync(str(p)) is False
    assert p.read_text(encoding="utf-8") == "{망가진"

    q = tmp_path / "skills.json"
    q.write_text("{망가진", encoding="utf-8")
    with pytest.raises(DataUnreadable):
        skills_catalog._previous(str(q))
    assert skills_catalog.sync(str(q)) is False
    assert q.read_text(encoding="utf-8") == "{망가진"
