"""스타 Δ 는 하루치여야 한다 (SPEC 1.5).

화면은 목록의 여러 줄에 "스타 +N" 을 나란히 보여준다. 어떤 줄은 하루치이고
어떤 줄은 38일치이면 그 숫자끼리 비교가 안 된다.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import build  # noqa: E402
from news.core import candidates  # noqa: E402

URL = "https://github.com/o/r"


def _seed(tmp_path, day, stars):
    from datetime import datetime
    when = datetime.fromisoformat(f"2026-09-{day:02d}T08:00:00+00:00")
    candidates.log([{"url": URL, "title": "t", "source": "github"}],
                   set(), when, {URL: {"stars": stars}}, str(tmp_path))


def test_스냅샷_날짜를_함께_돌려준다(tmp_path):
    """숫자만 주면 부른 쪽이 그게 언제 것인지 알 수 없다."""
    _seed(tmp_path, 18, 1000)
    assert candidates.previous_stars(URL, "2026-09-20", str(tmp_path)) == (1000, "2026-09-18")
    assert candidates.previous_stars(URL, "2026-09-18", str(tmp_path)) is None


def test_어제_스냅샷이면_빼서_쓴다():
    assert build._is_yesterday("2026-09-19", "2026-09-20")
    assert build._is_yesterday("2026-08-31", "2026-09-01")


def test_이틀_이상_벌어지면_쓰지_않는다():
    """어제 API 가 실패했거나(스냅샷 1,467개 중 9개) 그 레포가 며칠 만에 다시
    트렌딩에 올라온 경우다. 실측 918쌍 중 132쌍이 이틀 이상 벌어져 있다."""
    assert not build._is_yesterday("2026-09-18", "2026-09-20")
    assert not build._is_yesterday("2026-08-13", "2026-09-20")   # 38일
    assert not build._is_yesterday("2026-09-20", "2026-09-20")
    assert not build._is_yesterday("", "2026-09-20")


def _delta(monkeypatch, prev, stars, upvotes=42):
    """previous_stars 를 직접 갈아 끼운다. base_dir 기본값이 정의 시점에
    묶이므로 candidates.DIR 를 바꿔도 안 통한다 — 처음에 그렇게 썼다가
    한 건이 엉뚱한 이유로 통과했다."""
    monkeypatch.setattr(candidates, "github_meta", lambda url, token=None: {"stars": stars})
    monkeypatch.setattr(candidates, "previous_stars",
                        lambda url, before_date, base_dir=None: prev)
    arts = [{"url": URL, "source": "github", "upvotes": upvotes}]
    build.apply_star_delta(arts, "2026-09-20")
    return arts[0]["delta_stars"]


def test_간격이_벌어지면_trending의_하루치를_쓴다(monkeypatch):
    """며칠치 증가분 대신 trending 이 직접 주는 stars today 를 쓴다."""
    assert _delta(monkeypatch, (1000, "2026-09-14"), 9000) == 42     # 8000 이 아니다


def test_어제_것이면_그대로_뺀다(monkeypatch):
    assert _delta(monkeypatch, (1000, "2026-09-19"), 1120) == 120


def test_첫_등장은_trending_값을_쓴다(monkeypatch):
    assert _delta(monkeypatch, None, 5000) == 42


def test_스타가_줄어도_음수는_안_쓴다(monkeypatch):
    assert _delta(monkeypatch, (1200, "2026-09-19"), 1000) == 0
