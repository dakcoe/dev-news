"""API 링크 생존 확인 (api-link-health).

public-apis README는 커뮤니티 갱신이 느려 도메인이 사라졌거나 404가 된 항목이
그대로 남는다 — 무작위 60건 실측(2026-08-29)에서 8%가 죽은 링크였다.
목록에 싣기 전에 직접 두드려 보고 죽은 것을 뺀다.

설계상 지키는 두 가지
1) **오탐을 죽음으로 세지 않는다.** 403(봇 차단)·429(요청 과다)·5xx(일시 장애)는
   "응답은 한다"거나 "모르겠다"이지 죽음이 아니다. 실측에서 403이 난 jooble ·
   collinsdictionary · lviv 는 브라우저로는 멀쩡히 열린다.
2) **한 번의 사고로 목록이 증발하지 않는다.** 연속 `threshold`회 죽음이 쌓인
   URL만 빼고, 그래도 한 소스에서 `max_drop_ratio`를 넘게 빠지면 필터를 통째로
   건너뛴다 — Actions 러너의 네트워크가 통으로 막힌 회차 방어.

전수(2,000여 건)를 매 회차 두드리지는 않는다. 결과를 `data/api_health.json`에
누적하고 매 회차 예산만큼만 **새 URL 우선 → 오래된 것 순**으로 확인한다.
하루 3회 실행 × 600건이면 한 바퀴가 하루 남짓이다.
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import os
from datetime import datetime, timedelta, timezone

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

KST = timezone(timedelta(hours=9))

# 브라우저를 흉내 내지 않으면 봇 차단(403)이 늘어 오탐 판정 부담만 커진다.
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; dev-news link checker; "
                         "+https://github.com/public-apis/public-apis)",
           "Accept": "*/*"}

DEFAULTS = {"enabled": True, "per_run": 600, "workers": 24, "timeout": 8,
            "threshold": 2, "max_drop_ratio": 0.3}

# 응답 코드가 곧 죽음인 것들. 그 밖의 4xx는 "서버는 살아 있다"로 본다.
_DEAD_CODES = {404, 410}
# 비율 방어선은 표본이 있어야 뜻이 있다 — 항목이 이보다 적은 소스에는 적용하지 않는다.
_GUARD_MIN = 5

# 도메인이 없거나 포트가 닫혔다 = 확실한 죽음. 주소 자체가 틀린 경우도 같다.
# 타임아웃은 여기 없다 — 살아 있지만 느리거나 해외 요청을 막는 서버가 흔하다
# (한국 공공기관 사이트 다수가 이 모양으로 보인다). 인증서 오류도 없다 —
# probe가 검증을 끄고 한 번 더 두드려 응답 여부로 가른다.
_DEAD_ERRORS = {"dns", "refused", "badurl"}


def classify(code: int | None, err: str | None) -> str:
    """한 번의 확인 결과를 ok / dead / unknown 으로 판정한다."""
    if code is None:
        return "dead" if err in _DEAD_ERRORS else "unknown"
    if code in _DEAD_CODES:
        return "dead"
    if code >= 500:
        return "unknown"        # 일시 장애일 수 있다 — 다음 회차에 다시 본다
    return "ok"                 # 2xx·3xx는 물론 401·403·429도 "응답은 한다"


def _error_kind(exc: Exception) -> str:
    """requests 예외를 판정에 쓸 몇 갈래로 줄인다.

    ConnectionError 하나에 DNS 실패·연결 거부·중간 끊김이 모두 들어오므로
    메시지를 봐야 갈래가 갈린다.
    """
    name = type(exc).__name__
    msg = str(exc)
    if name in ("InvalidURL", "MissingSchema", "InvalidSchema", "LocationParseError"):
        return "badurl"
    if name in ("ConnectTimeout", "ReadTimeout", "Timeout"):
        return "timeout"
    if "NameResolutionError" in msg or "getaddrinfo" in msg or "Name or service not known" in msg:
        return "dns"
    if "refused" in msg.lower() or "No route to host" in msg:
        return "refused"
    if name == "SSLError":
        return "ssl"
    return name


def probe(url: str, timeout: float = 8) -> tuple[int | None, str | None]:
    """URL 하나를 두드려 (상태코드, 예외이름)을 돌려준다.

    본문은 필요 없으므로 stream으로 헤더만 받고 닫는다. HEAD를 안 쓰는 이유는
    HEAD만 405로 막는 서버가 흔해서다 — 그러면 살아있는 곳을 못 본다.
    """
    def get(**kw):
        r = requests.get(url, headers=HEADERS, timeout=timeout,
                         allow_redirects=True, stream=True, **kw)
        code = r.status_code
        r.close()
        return code

    try:
        return get(), None
    except Exception as e:                      # requests 예외 계층이 넓다
        kind = _error_kind(e)

    if kind == "ssl":
        # 인증서가 낡았을 뿐 서버는 살아 있는 곳이 많다 — 한국 공공기관 사이트가
        # 특히 그렇다. 검증을 끄고 한 번 더 두드려 "응답은 하는지"만 본다.
        try:
            return get(verify=False), "ssl"
        except Exception as e2:
            return None, _error_kind(e2)
    return None, kind


def _targets(apis: list[dict], cache: dict, budget: int) -> list[str]:
    """이번 회차에 확인할 URL — 한 번도 안 본 것 먼저, 그 다음 오래된 순."""
    urls = list(dict.fromkeys(a["url"] for a in apis))
    urls.sort(key=lambda u: (cache.get(u, {}).get("at") or ""))
    return urls[:budget]


def update(apis: list[dict], cache: dict, budget: int = 600,
           workers: int = 24, timeout: float = 8) -> dict:
    """예산만큼 확인해 캐시를 갱신한다(제자리 수정). 요약 dict를 돌려준다."""
    live = {a["url"] for a in apis}
    for gone in [u for u in cache if u not in live]:
        del cache[gone]                          # 목록에서 빠진 URL은 캐시도 정리

    targets = _targets(apis, cache, budget)
    now = datetime.now(KST).isoformat()
    counts = {"ok": 0, "dead": 0, "unknown": 0}

    def one(url):
        code, err = probe(url, timeout=timeout)
        return url, classify(code, err), code, err

    if targets:
        with cf.ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            results = list(ex.map(one, targets))
    else:
        results = []

    for url, verdict, code, err in results:
        entry = cache.setdefault(url, {"fails": 0})
        entry["code"], entry["err"] = code, err
        counts[verdict] += 1
        if verdict == "ok":
            entry["fails"] = 0
        elif verdict == "dead":
            entry["fails"] = entry.get("fails", 0) + 1
        entry["state"] = verdict
        entry["at"] = now
    return {"checked": len(targets), **counts}


def apply(apis: list[dict], cache: dict, threshold: int = 2,
          max_drop_ratio: float = 0.3) -> tuple[list[dict], int]:
    """연속 실패가 임계에 닿은 항목을 뺀다. (남은 목록, 제외 건수)

    한 소스에서 `max_drop_ratio`를 넘게 빠지면 그 소스는 손대지 않는다 —
    러너 네트워크가 통으로 막힌 회차에 목록이 증발하는 쪽이 훨씬 큰 사고다.
    """
    def is_dead(a):
        return cache.get(a["url"], {}).get("fails", 0) >= threshold

    by_src: dict[str, list[dict]] = {}
    for a in apis:
        by_src.setdefault(a.get("src", ""), []).append(a)

    keep_urls: set[int] = set()
    dropped = 0
    for src, items in by_src.items():
        dead = [a for a in items if is_dead(a)]
        if len(items) >= _GUARD_MIN and len(dead) / len(items) > max_drop_ratio:
            print(f"[apis] {src}: 죽은 링크 {len(dead)}/{len(items)}건 — 비율이 높아 "
                  f"필터를 건너뛴다(네트워크 이상 의심)")
            keep_urls.update(id(a) for a in items)
            continue
        dropped += len(dead)
        keep_urls.update(id(a) for a in items if not is_dead(a))

    return [a for a in apis if id(a) in keep_urls], dropped


def load_cache(path: str) -> dict:
    """캐시를 읽는다. 없거나 깨졌으면 빈 캐시 — 확인을 다시 하면 그만이다."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_cache(path: str, cache: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)


def run(apis: list[dict], cache_path: str, cfg: dict | None = None) -> tuple[list[dict], dict]:
    """확인 → 캐시 저장 → 필터. (남은 목록, 요약)"""
    c = {**DEFAULTS, **(cfg or {})}
    cache = load_cache(cache_path)
    summary = update(apis, cache, budget=c["per_run"], workers=c["workers"],
                     timeout=c["timeout"])
    save_cache(cache_path, cache)
    kept, dropped = apply(apis, cache, threshold=c["threshold"],
                          max_drop_ratio=c["max_drop_ratio"])
    summary["dropped"] = dropped
    summary["known"] = len(cache)
    return kept, summary
