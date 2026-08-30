"""공용 유틸 (consolidate-shared-utils).

재현하는 결함: 날짜 파싱 사본이 갈라져 있었다. rss._ts는 tzinfo 없는 datetime을
UTC로 보정했지만 geeknews._to_ts는 하지 않았다. naive datetime에 .astimezone()을
부르면 파이썬이 로컬 시각으로 해석하므로, 같은 피드가 로컬(KST)과 Actions(UTC)에서
9시간 다른 값으로 저장된다 — recent_only의 48시간 창 판정이 환경에 따라 달라졌다.
"""
import os
import sys
from datetime import datetime, timezone

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from news.core.common import KST, ROOT, to_timestamp  # noqa: E402


def _utc(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp()


# ------------------------------------------------------------------ 형식별 파싱
def test_rfc2822_with_timezone():
    assert to_timestamp("Wed, 20 Aug 2026 12:00:00 +0000") == _utc(2026, 8, 20, 12)


def test_iso8601_with_offset():
    assert to_timestamp("2026-08-20T12:00:00+00:00") == _utc(2026, 8, 20, 12)


def test_iso8601_with_z_suffix():
    assert to_timestamp("2026-08-20T12:00:00Z") == _utc(2026, 8, 20, 12)


def test_kst_offset_is_converted():
    assert to_timestamp("2026-08-20T21:00:00+09:00") == _utc(2026, 8, 20, 12)


def test_numeric_input_passes_through():
    assert to_timestamp(1787000000) == 1787000000.0
    assert to_timestamp("1787000000") == 1787000000.0
    assert to_timestamp(1787000000.5) == 1787000000.5


# --------------------------------------------------------- naive는 항상 UTC (버그)
def test_naive_iso_is_utc_not_local():
    """이 프로젝트의 실제 버그 — geeknews가 naive를 로컬로 해석했다."""
    assert to_timestamp("2026-08-20T12:00:00") == _utc(2026, 8, 20, 12)


def test_naive_rfc2822_is_utc_not_local():
    assert to_timestamp("20 Aug 2026 12:00:00") == _utc(2026, 8, 20, 12)


def test_geeknews_and_rss_agree():
    """두 사본이 갈라져 있었다 — 같은 입력에 같은 값이어야 한다."""
    for value in ("Wed, 20 Aug 2026 12:00:00 +0000",
                  "2026-08-20T12:00:00Z",
                  "2026-08-20T12:00:00"):
        assert to_timestamp(value) == _utc(2026, 8, 20, 12), value


# ------------------------------------------------------------------ 잘못된 입력
def test_bad_input_returns_none():
    for bad in (None, "", "  ", "not a date", "2026-13-45", [], {}):
        assert to_timestamp(bad) is None, repr(bad)


def test_returns_float():
    assert isinstance(to_timestamp("2026-08-20T12:00:00Z"), float)


# ------------------------------------------------------------------ 상수
def test_kst_is_plus_nine():
    assert KST.utcoffset(None).total_seconds() == 9 * 3600


def test_root_points_at_project():
    assert os.path.isfile(os.path.join(ROOT, "build.py"))
    assert os.path.isdir(os.path.join(ROOT, "news"))
