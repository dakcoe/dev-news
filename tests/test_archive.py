"""월별 샤딩·마이그레이션 회귀 테스트 (SPEC 2.1 검수 기준)."""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from news.core import archive  # noqa: E402

KST = timezone(timedelta(hours=9))


def _art(url, batch):
    return {"url": url, "title": url, "batch": batch}


def test_append_creates_month_shard(tmp_path):
    base = str(tmp_path / "articles")
    now = datetime(2026, 8, 6, 9, 0, tzinfo=KST)
    archive.append([{"url": "https://a", "title": "a"}], now, base_dir=base)
    shard = json.load(open(os.path.join(base, "2026-08.json"), encoding="utf-8"))
    assert len(shard) == 1 and shard[0]["batch"].startswith("2026-08-06")


def test_append_no_duplicates_and_no_trim(tmp_path):
    base = str(tmp_path / "articles")
    now = datetime(2026, 8, 6, 9, 0, tzinfo=KST)
    archive.append([{"url": "https://a", "title": "a"}], now, base_dir=base)
    merged = archive.append([{"url": "https://a"}, {"url": "https://b"}], now, base_dir=base)
    assert len(merged) == 2                       # a 중복 제외, 상한 삭제 없음


def test_append_only_touches_current_month(tmp_path):
    base = str(tmp_path / "articles")
    old = datetime(2026, 7, 1, 9, 0, tzinfo=KST)
    archive.append([{"url": "https://old", "title": "old"}], old, base_dir=base)
    before = open(os.path.join(base, "2026-07.json"), encoding="utf-8").read()

    now = datetime(2026, 8, 6, 9, 0, tzinfo=KST)
    archive.append([{"url": "https://new", "title": "new"}], now, base_dir=base)
    after = open(os.path.join(base, "2026-07.json"), encoding="utf-8").read()
    assert before == after                        # 지난 달 샤드는 불변


def test_migrate_legacy_idempotent(tmp_path):
    base = str(tmp_path / "articles")
    legacy = str(tmp_path / "articles.json")
    items = [_art("https://x", "2026-07-30T09:00:00+09:00"),
             _art("https://y", "2026-08-01T09:00:00+09:00")]
    json.dump(items, open(legacy, "w", encoding="utf-8"))

    archive.migrate_legacy(legacy_path=legacy, base_dir=base)
    assert not os.path.exists(legacy)
    assert sorted(archive.months(base)) == ["2026-07", "2026-08"]
    assert len(archive.load_all(base)) == 2

    archive.migrate_legacy(legacy_path=legacy, base_dir=base)   # 두 번 실행해도 안전
    assert len(archive.load_all(base)) == 2


def test_recent_display_window():
    now = datetime.now(timezone.utc)
    fresh = _art("https://f", now.isoformat())
    stale = _art("https://s", (now - timedelta(days=40)).isoformat())
    kept = archive.recent([fresh, stale], 30)
    assert [a["url"] for a in kept] == ["https://f"]
    assert len(archive.recent([fresh, stale], 0)) == 2          # 0 = 전체


def test_search_index_light(tmp_path):
    path = str(tmp_path / "search-index.json")
    archive.write_search_index(
        [{"url": "https://a", "title": "t", "ko_title": "번역", "source": "rss",
          "batch": "2026-08-06T09:00:00+09:00", "summary": "긴 요약" * 100}], path=path)
    idx = json.load(open(path, encoding="utf-8"))
    assert idx == [{"t": "번역", "u": "https://a", "m": "2026-08", "s": "rss", "d": "2026-08-06"}]
