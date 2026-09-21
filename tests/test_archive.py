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
    """항목은 가볍게. 요약 본문이 섞이면 방문자마다 그만큼 더 받는다."""
    path = str(tmp_path / "search-index.json")
    archive.write_search_index(
        [{"url": "https://a", "title": "t", "ko_title": "번역", "source": "rss",
          "batch": "2026-08-06T09:00:00+09:00", "summary": "긴 요약" * 100}], path=path)
    rows = json.load(open(tmp_path / "search-index-2026-08.json", encoding="utf-8"))
    assert rows == [{"t": "번역", "u": "https://a", "m": "2026-08", "s": "rss",
                     "g": [], "d": "2026-08-06"}]


def test_search_index_is_sharded_by_month(tmp_path):
    """한 파일에 전부 담으면 회차마다 그 파일 전체가 새로 커밋된다. 지난 달 것은
    바뀌지 않아야 한다."""
    path = str(tmp_path / "search-index.json")
    arts = [{"url": f"https://a/{i}", "title": f"t{i}", "source": "rss",
             "batch": f"2026-0{8 if i < 2 else 9}-06T09:00:00+09:00"}
            for i in range(4)]
    archive.write_search_index(arts, path=path)

    manifest = json.load(open(path, encoding="utf-8"))
    assert manifest == {"months": ["2026-08", "2026-09"]}
    assert len(json.load(open(tmp_path / "search-index-2026-08.json", encoding="utf-8"))) == 2
    assert len(json.load(open(tmp_path / "search-index-2026-09.json", encoding="utf-8"))) == 2

    # 이번 달에만 기사가 늘어도 지난 달 파일은 그대로다
    before = (tmp_path / "search-index-2026-08.json").read_bytes()
    arts.append({"url": "https://a/9", "title": "t9", "source": "rss",
                 "batch": "2026-09-07T09:00:00+09:00"})
    archive.write_search_index(arts, path=path)
    assert (tmp_path / "search-index-2026-08.json").read_bytes() == before


def test_못_읽는_샤드를_덮어쓰지_않는다(tmp_path):
    """append() 는 `새 기사 + 기존 샤드` 를 같은 경로에 바로 저장한다. 읽기
    실패를 빈 목록으로 처리하면 파싱이 한 번 어긋나는 것만으로 그달 기사가
    새 기사만 남기고 사라진다."""
    import json
    from datetime import datetime, timezone
    import pytest
    from news.core import archive

    when = datetime(2026, 9, 1, tzinfo=timezone.utc)
    archive.append([{"url": "https://e.com/1", "title": "t"}], when, str(tmp_path))
    shard = tmp_path / "2026-09.json"
    before = shard.read_text(encoding="utf-8")

    shard.write_text("{망가진 JSON", encoding="utf-8")
    with pytest.raises(archive.ShardUnreadable):
        archive.append([{"url": "https://e.com/2", "title": "t2"}], when, str(tmp_path))
    # 원본이 남아 있어야 되살릴 수 있다
    assert shard.read_text(encoding="utf-8") == "{망가진 JSON"

    shard.write_text(before, encoding="utf-8")
    assert len(archive.load_all(str(tmp_path))) == 1

    # 목록이 아닌 JSON 도 같다
    shard.write_text(json.dumps({"url": "x"}), encoding="utf-8")
    with pytest.raises(archive.ShardUnreadable):
        archive.load_all(str(tmp_path))
