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
    assert out[0]["resurfaced"] == (datetime.now(timezone.utc) - timedelta(days=100)).date().isoformat()


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
