"""api-link-health 회귀 테스트 — 죽은 API 링크 걸러내기.

public-apis README에는 도메인이 사라졌거나 404가 된 항목이 그대로 남는다.
링크를 직접 두드려 확인하되, 봇 차단(403)·요청 과다(429)·일시 장애(5xx)를
죽음으로 오판하지 않는 것이 이 모듈의 전부다.
"""
import json
from unittest.mock import patch

from news import api_health as H


def apis(*urls):
    return [{"name": f"A{i}", "url": u, "desc": "", "auth": "",
             "cat": "Test", "src": "global"} for i, u in enumerate(urls)]


# ---------------- 판정표 ----------------

def test_응답하면_살아있다():
    for code in (200, 204, 301, 302, 401, 403, 405, 429, 451):
        assert H.classify(code, None) == "ok", code


def test_없는_페이지는_죽음():
    assert H.classify(404, None) == "dead"
    assert H.classify(410, None) == "dead"


def test_도메인이_없거나_연결이_거부되면_죽음():
    for err in ("dns", "refused", "badurl"):
        assert H.classify(None, err) == "dead"


def test_타임아웃과_일시_장애는_판단보류():
    """느린 서버·해외 요청 차단을 죽음으로 세면 멀쩡한 API가 사라진다.

    실측: 한국 공공기관 사이트 여럿이 ConnectTimeout·SSLError로 보이는데
    브라우저로는 정상이다.
    """
    assert H.classify(500, None) == "unknown"
    assert H.classify(503, None) == "unknown"
    assert H.classify(None, "timeout") == "unknown"
    assert H.classify(None, "ChunkedEncodingError") == "unknown"


def test_인증서_오류는_응답만_하면_살아있다():
    """probe가 검증을 끄고 재시도해 응답을 받으면 코드가 실려 온다."""
    assert H.classify(200, "ssl") == "ok"


def test_예외를_갈래로_줄인다():
    import requests as R
    assert H._error_kind(R.exceptions.ConnectTimeout("x")) == "timeout"
    assert H._error_kind(R.exceptions.ConnectionError(
        "HTTPSConnectionPool: NameResolutionError ...")) == "dns"
    assert H._error_kind(R.exceptions.ConnectionError(
        "[Errno 111] Connection refused")) == "refused"
    assert H._error_kind(R.exceptions.SSLError("bad cert")) == "ssl"
    assert H._error_kind(R.exceptions.MissingSchema("nope")) == "badurl"


def test_인증서_오류면_검증을_끄고_한_번_더_두드린다():
    import requests as R
    calls = []

    def fake_get(url, **kw):
        calls.append(kw.get("verify", True))
        if kw.get("verify", True):
            raise R.exceptions.SSLError("expired")
        return type("R", (), {"status_code": 200, "close": lambda self: None})()

    with patch.object(H.requests, "get", fake_get):
        assert H.probe("https://oldcert.test/") == (200, "ssl")
    assert calls == [True, False]


# ---------------- 캐시 누적 ----------------

def test_연속_실패가_임계에_닿아야_제외된다():
    items = apis("https://dead.test/")
    cache = {}
    with patch.object(H, "probe", return_value=(404, None)):
        H.update(items, cache, budget=10)
    assert cache["https://dead.test/"]["fails"] == 1
    kept, dropped = H.apply(items, cache, threshold=2)
    assert len(kept) == 1 and dropped == 0      # 1회로는 안 뺀다

    with patch.object(H, "probe", return_value=(404, None)):
        H.update(items, cache, budget=10)
    kept, dropped = H.apply(items, cache, threshold=2)
    assert kept == [] and dropped == 1


def test_다시_살아나면_복구된다():
    items = apis("https://flaky.test/")
    cache = {"https://flaky.test/": {"fails": 3, "code": 404, "at": "2020-01-01"}}
    with patch.object(H, "probe", return_value=(200, None)):
        H.update(items, cache, budget=10)
    assert cache["https://flaky.test/"]["fails"] == 0
    assert H.apply(items, cache, threshold=2)[0] == items


def test_판단보류는_실패로_세지_않는다():
    items = apis("https://slow.test/")
    cache = {"https://slow.test/": {"fails": 1, "code": 404, "at": "2020-01-01"}}
    with patch.object(H, "probe", return_value=(503, None)):
        H.update(items, cache, budget=10)
    assert cache["https://slow.test/"]["fails"] == 1     # 그대로


# ---------------- 안전장치 ----------------

def test_한_소스가_통째로_죽으면_필터를_건너뛴다():
    """러너 네트워크가 통으로 막힌 회차에 목록이 증발하면 안 된다."""
    items = apis(*[f"https://x{i}.test/" for i in range(10)])
    cache = {a["url"]: {"fails": 5, "code": None, "at": "2020-01-01"} for a in items}
    kept, dropped = H.apply(items, cache, threshold=2, max_drop_ratio=0.3)
    assert kept == items and dropped == 0


def test_예산만큼만_확인한다():
    items = apis(*[f"https://x{i}.test/" for i in range(10)])
    with patch.object(H, "probe", return_value=(200, None)) as p:
        H.update(items, {}, budget=3)
    assert p.call_count == 3


def test_확인_안_된_URL부터_확인한다():
    items = apis("https://old.test/", "https://new.test/")
    cache = {"https://old.test/": {"fails": 0, "code": 200, "at": "2026-08-29T00:00:00+09:00"}}
    seen = []
    with patch.object(H, "probe", side_effect=lambda u, **k: seen.append(u) or (200, None)):
        H.update(items, cache, budget=1)
    assert seen == ["https://new.test/"]


def test_목록에서_사라진_URL은_캐시에서도_치운다():
    items = apis("https://live.test/")
    cache = {"https://live.test/": {"fails": 0, "code": 200, "at": "x"},
             "https://gone.test/": {"fails": 0, "code": 200, "at": "x"}}
    with patch.object(H, "probe", return_value=(200, None)):
        H.update(items, cache, budget=10)
    assert "https://gone.test/" not in cache


# ---------------- 파일 입출력 ----------------

def test_캐시_저장과_로드(tmp_path):
    p = str(tmp_path / "api_health.json")
    assert H.load_cache(p) == {}                 # 없으면 빈 캐시
    H.save_cache(p, {"https://a.test/": {"fails": 1, "code": 404, "at": "x"}})
    assert H.load_cache(p)["https://a.test/"]["fails"] == 1


def test_깨진_캐시는_빈_캐시로_시작한다(tmp_path):
    p = str(tmp_path / "api_health.json")
    with open(p, "w", encoding="utf-8") as f:
        f.write("{ not json")
    assert H.load_cache(p) == {}


# ---------------- 카탈로그 연결 ----------------

def test_카탈로그가_죽은_링크를_빼고_요약을_남긴다(tmp_path):
    from news import apis_catalog

    catalog = {"updated": "x", "sources": [{"id": "global", "label": "L", "home": "h", "count": 2}],
               "apis": apis("https://ok.test/", "https://dead.test/")}
    cache_path = str(tmp_path / "api_health.json")
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump({"https://dead.test/": {"fails": 2, "code": 404, "at": "x"}}, f)

    with patch.object(apis_catalog, "build_catalog", return_value=catalog), \
         patch.object(H, "probe", return_value=(404, None)):
        out = str(tmp_path / "apis.json")
        assert apis_catalog.sync(out, health={"enabled": True, "per_run": 0},
                                 cache_path=cache_path)
        data = json.load(open(out, encoding="utf-8"))

    assert [a["url"] for a in data["apis"]] == ["https://ok.test/"]
    assert data["sources"][0]["count"] == 1          # 소스 건수도 제외 후 값
    assert data["health"]["dropped"] == 1


def test_링크_확인이_꺼져_있으면_그대로_통과한다(tmp_path):
    from news import apis_catalog

    catalog = {"updated": "x", "sources": [{"id": "global", "label": "L", "home": "h", "count": 2}],
               "apis": apis("https://ok.test/", "https://dead.test/")}
    with patch.object(apis_catalog, "build_catalog", return_value=catalog):
        out = str(tmp_path / "apis.json")
        apis_catalog.sync(out, health={"enabled": False})
        data = json.load(open(out, encoding="utf-8"))
    assert len(data["apis"]) == 2 and "health" not in data


def test_확인_실패해도_회차를_죽이지_않는다(tmp_path):
    from news import apis_catalog

    catalog = {"updated": "x", "sources": [], "apis": apis("https://ok.test/")}
    with patch.object(apis_catalog, "build_catalog", return_value=catalog), \
         patch.object(H, "run", side_effect=RuntimeError("boom")):
        out = str(tmp_path / "apis.json")
        assert apis_catalog.sync(out, health={"enabled": True},
                                 cache_path=str(tmp_path / "c.json"))
        assert len(json.load(open(out, encoding="utf-8"))["apis"]) == 1
