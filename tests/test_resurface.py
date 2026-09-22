"""기간이 지나면 다시 실을 수 있는 출처 (seen.resurface_days).

한 번 실린 URL 은 영구히 막힌다. 그런데 깃허브 저장소는 몇 달 뒤 새 릴리스로
다시 트렌딩에 오르는 일이 흔하고, 그때 옛 기사만 남아 있으면 지금 상태를 알 수
없다. 출처별로 지정한 날짜가 지나면 다시 후보가 되고 '다시 트렌딩'이 붙는다.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from news.core import seen as S  # noqa: E402
from news.core.common import KST  # noqa: E402

RULE = {"github": 90}


def _seen_file(tmp_path, ago_days, value=None):
    at = value or (datetime.now(timezone.utc) - timedelta(days=ago_days)).isoformat()
    p = tmp_path / "seen.json"
    p.write_text(json.dumps({"https://github.com/a/b": at, "https://news.example/x": at}), encoding="utf-8")
    return str(p)


GH = {"title": "a/b", "url": "https://github.com/a/b", "source": "github"}
HN = {"title": "x", "url": "https://news.example/x", "source": "hackernews"}


def test_기간이_지난_깃허브_저장소는_다시_후보가_된다(tmp_path):
    out = S.filter_unseen([GH, HN], _seen_file(tmp_path, 100), resurface_days=RULE)
    assert [a["url"] for a in out] == [GH["url"]]
    assert out[0]["resurfaced"] == (datetime.now(KST) - timedelta(days=100)).date().isoformat()


def test_기간이_안_지났으면_여전히_막힌다(tmp_path):
    assert S.filter_unseen([GH], _seen_file(tmp_path, 10), resurface_days=RULE) == []


def test_규칙에_없는_출처는_영구히_막힌다(tmp_path):
    assert S.filter_unseen([HN], _seen_file(tmp_path, 400), resurface_days=RULE) == []


def test_규칙이_없으면_종전과_같다(tmp_path):
    assert S.filter_unseen([GH, HN], _seen_file(tmp_path, 400)) == []


def test_기록_시각을_못_읽으면_본_것으로_친다(tmp_path):
    assert S.filter_unseen([GH], _seen_file(tmp_path, 0, value="언제인지 모름"), resurface_days=RULE) == []


def test_다시_실리면_기록이_지금으로_갱신된다(tmp_path):
    """그래야 그때부터 다시 90일을 센다. 옛 시각이 남으면 매 회차 다시 실린다."""
    p = _seen_file(tmp_path, 100)
    S.mark_seen([GH], p)
    at = datetime.fromisoformat(json.loads(open(p, encoding="utf-8").read())["github.com/a/b"])
    assert (datetime.now(timezone.utc) - at).days == 0


def test_설정과_화면이_연결돼_있다():
    import yaml
    cfg = yaml.safe_load(open(os.path.join(ROOT, "config.yaml"), encoding="utf-8"))
    assert cfg["seen"]["resurface_days"]["github"] == 30
    b = open(os.path.join(ROOT, "build.py"), encoding="utf-8").read()
    assert 'resurface_days=(cfg.get("seen") or {}).get("resurface_days")' in b
    r = open(os.path.join(ROOT, "news", "render.py"), encoding="utf-8").read()
    assert '"again": a.get("resurfaced")' in r
    t = open(os.path.join(ROOT, "news", "template.html"), encoding="utf-8").read()
    assert "다시 트렌딩" in t and "again:d.again" in t


def test_병합은_URL과_회차로_가린다():
    """다시 트렌딩에 오른 저장소는 같은 URL 로 다른 회차에 한 번 더 실린다.
    URL 만으로 가리면 그 항목이 병합에서 사라진다."""
    from scripts.merge_remote_data import _insert_by_batch  # noqa: F401  (임포트 가능 확인)
    src = open(os.path.join(ROOT, "scripts", "merge_remote_data.py"), encoding="utf-8").read()
    assert 'a.get("batch") or "")' in src and "key(a) not in have" in src


def test_재등장_기사는_아카이브에_다시_쌓인다(tmp_path):
    """seen 이 기간을 보고 통과시킨 기사를 archive 가 주소 중복으로 버리면,
    요약을 새로 만들어 놓고 저장하지 않는다 — 다시 트렌딩이 화면에 안 뜬다."""
    from datetime import datetime, timezone
    from news.core import archive
    url = "https://github.com/x/y"
    first = datetime(2026, 6, 1, tzinfo=timezone.utc)
    again = datetime(2026, 9, 1, tzinfo=timezone.utc)

    archive.append([{"url": url, "title": "t"}], first, str(tmp_path))
    # 같은 주소를 그냥 다시 넣으면 걸러진다
    archive.append([{"url": url, "title": "t"}], again, str(tmp_path))
    assert len(archive.load_all(str(tmp_path))) == 1
    # resurfaced 가 붙으면 새 회차로 쌓인다
    archive.append([{"url": url, "title": "t", "resurfaced": "2026-06-01"}], again, str(tmp_path))
    rows = archive.load_all(str(tmp_path))
    assert len(rows) == 2
    assert any(r.get("resurfaced") for r in rows)


def test_재등장_기사가_회차마다_쌓이지_않는다(tmp_path):
    """저장 뒤 렌더나 푸시가 실패하면 seen 만 남고 아카이브는 롤백되지 않는다.
    resurfaced 를 무조건 통과시키면 그 다음 회차마다 같은 기사가 또 쌓인다."""
    from datetime import datetime, timedelta, timezone
    from news.core import archive
    url = "https://github.com/x/y"
    first = datetime(2026, 6, 1, tzinfo=timezone.utc)
    archive.append([{"url": url, "title": "t"}], first, str(tmp_path))

    again = datetime(2026, 9, 1, tzinfo=timezone.utc)
    item = {"url": url, "title": "t", "resurfaced": "2026-06-01"}
    archive.append([item], again, str(tmp_path))
    assert len(archive.load_all(str(tmp_path))) == 2

    # 같은 재등장을 다시 보내도 늘지 않는다 — 이미 그 재등장으로 실렸다
    archive.append([item], again + timedelta(hours=8), str(tmp_path))
    archive.append([item], again + timedelta(hours=16), str(tmp_path))
    assert len(archive.load_all(str(tmp_path))) == 2

    # 더 뒤에 다시 트렌딩에 오르면 그때는 받는다
    later = {"url": url, "title": "t", "resurfaced": "2026-09-01"}
    archive.append([later], datetime(2026, 12, 1, tzinfo=timezone.utc), str(tmp_path))
    assert len(archive.load_all(str(tmp_path))) == 3


def test_자정_회차에_실린_저장소도_재등장하면_아카이브에_쌓인다(tmp_path):
    """KST 00시 회차는 seen 에 UTC 로 전날 날짜로 적힌다. 재등장 날짜를 UTC 로
    뽑으면 아카이브의 KST 회차 날짜보다 하루 앞서, 요약을 받고도 저장되지 않았다."""
    from news.core import archive
    from news.core.common import KST

    url = "https://github.com/a/b"
    shards = str(tmp_path / "articles")
    first = datetime.now(KST).replace(hour=0, minute=5) - timedelta(days=40)
    archive.append([{"url": url, "title": "t"}], first, shards)
    seen_at = (first + timedelta(minutes=1)).astimezone(timezone.utc).isoformat()
    p = tmp_path / "seen.json"
    p.write_text(json.dumps({url: seen_at}), encoding="utf-8")

    back = S.filter_unseen([GH], str(p), resurface_days={"github": 30})
    assert back and back[0]["resurfaced"] == first.date().isoformat()
    archive.append(back, datetime.now(KST), shards)
    assert len(archive.load_all(shards)) == 2
