"""add-ad-slot 회귀 테스트 — 페이지 광고 자리.

config.yaml의 `ads` 블록 하나로 켜고 끈다. 핵심은 두 가지다:
설정이 조금이라도 이상하면 광고를 끄고(fail closed), 꺼져 있으면 결과 HTML에
광고 흔적이 남지 않는다.
"""
import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from news.render import _ads_config, render  # noqa: E402

ADSENSE = {"enabled": True, "provider": "adsense",
           "client": "ca-pub-1234567890123456", "slot": "9876543210",
           "count": 1}


@pytest.fixture(scope="module")
def articles():
    with open(os.path.join(ROOT, "sample.json"), encoding="utf-8") as f:
        return json.load(f)


def build(tmp_path, articles, ads):
    out = tmp_path / "index.html"
    render(articles, str(out), ads=ads)
    return out.read_text(encoding="utf-8")


# ---------------- 꺼짐이 기본 ----------------

def test_설정이_없으면_광고가_나가지_않는다(tmp_path, articles):
    """광고를 그리는 JS는 템플릿에 늘 들어 있지만 ADS가 null이면 아무것도
    그리지 않는다 — 확인할 것은 외부 요청이 없다는 점과 설정이 null이라는 점."""
    html = build(tmp_path, articles, None)
    assert "googlesyndication.com" not in html
    assert "__ADS_HEAD__" not in html and "__ADS_JSON__" not in html
    assert "const ADS = null;" in html


def test_enabled가_false면_꺼진다():
    assert _ads_config({**ADSENSE, "enabled": False}) is None


# ---------------- placeholder ----------------

def test_placeholder는_외부_스크립트를_부르지_않는다(tmp_path, articles):
    html = build(tmp_path, articles, {"enabled": True, "provider": "placeholder"})
    assert "googlesyndication.com" not in html
    assert '"provider": "placeholder"' in html.replace("'", '"')


# ---------------- adsense ----------------

def test_애드센스_스크립트는_정확히_한_번(tmp_path, articles):
    html = build(tmp_path, articles, ADSENSE)
    assert html.count("pagead2.googlesyndication.com/pagead/js/adsbygoogle.js") == 1
    assert "client=ca-pub-1234567890123456" in html


def test_설정값이_그대로_전달된다(tmp_path, articles):
    html = build(tmp_path, articles, ADSENSE)
    cfg = json.loads(re.search(r"const ADS = (\{.*?\});", html).group(1))
    assert cfg == {"provider": "adsense", "client": "ca-pub-1234567890123456",
                   "slot": "9876543210", "count": 1}


# ---------------- 잘못된 설정은 끈다 ----------------

@pytest.mark.parametrize("client", [
    "", "pub-1234567890123456", "ca-pub-", "ca-pub-abc",
    'ca-pub-1"></script><script>alert(1)</script>',
    "ca-pub-1234567890123456 onload=alert(1)",
])
def test_이상한_client는_광고를_끈다(client):
    assert _ads_config({**ADSENSE, "client": client}) is None


@pytest.mark.parametrize("slot", ["", "abc", "12", "98765<script>"])
def test_이상한_slot은_광고를_끈다(slot):
    assert _ads_config({**ADSENSE, "slot": slot}) is None


def test_모르는_provider는_광고를_끈다():
    assert _ads_config({**ADSENSE, "provider": "taboola"}) is None


def test_주입_시도가_HTML에_들어가지_않는다(tmp_path, articles):
    html = build(tmp_path, articles, {**ADSENSE, "client": 'ca-pub-1"><script>alert(1)</script>'})
    assert "alert(1)" not in html
    assert "googlesyndication.com" not in html      # 광고 자체가 꺼진다
    assert "const ADS = null;" in html


# ---------------- 개수 ----------------

def test_개수는_상한을_넘지_않는다():
    """레일이 광고탑이 되면 안 된다 — 요청이 99개여도 3개까지."""
    assert _ads_config({**ADSENSE, "count": 99})["count"] == 3


def test_count가_0이면_광고를_끈다():
    assert _ads_config({**ADSENSE, "count": 0}) is None


def test_망가진_값에도_죽지_않는다():
    assert _ads_config({**ADSENSE, "count": "한개"}) is None
    assert _ads_config("광고켜줘") is None


# ---------------- 중복 초기화 방지 ----------------

def test_이미_채워진_광고는_다시_초기화하지_않는다(tmp_path, articles):
    """renderList()가 검색 한 글자마다 목록을 다시 그린다 — 그때마다 push하면
    애드센스가 'already have ads' 오류를 낸다."""
    html = build(tmp_path, articles, ADSENSE)
    assert "ins.adsbygoogle:not([data-adsbygoogle-status])" in html


def test_기사_사이가_아니라_오른쪽_레일에_넣는다(tmp_path, articles):
    """사용자 요청: 읽는 흐름을 끊는 인피드 광고는 넣지 않는다."""
    html = build(tmp_path, articles, ADSENSE)
    assert "adRailHTML()" in html
    assert "withAds(" not in html                    # 인피드 삽입 경로가 남아 있지 않다
    assert ".adrail{display:none" in html            # 기본은 숨김 — 넓은 화면에서만 뜬다
    assert "body.ads .layout .adrail{display:block}" in html


def test_광고_개수만큼_레일에_쌓인다(tmp_path, articles):
    html = build(tmp_path, articles, {**ADSENSE, "count": 3})
    cfg = json.loads(re.search(r"const ADS = (\{.*?\});", html).group(1))
    assert cfg["count"] == 3
    assert "for(let i=0;i<ADS.count;i++)" in html


def test_광고_라벨이_붙는다(tmp_path, articles):
    """표시광고법·애드센스 정책 모두 광고임을 알아볼 수 있어야 한다."""
    html = build(tmp_path, articles, ADSENSE)
    assert "광고" in html
