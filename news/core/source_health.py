"""출처별 수집 건수 기록과 침묵 감지 (add-source-silence-alert).

github·trendshift·anthropic은 HTML을 파싱한다. 상대 사이트가 화면을 바꾸면
에러가 아니라 0건이 나온다. 다른 출처가 top_n을 채우면 게시 건수 기반
열화 알림(alert.min_published)에는 안 걸리므로, 출처 단위로 따로 본다.

한 회차 0건은 정상일 수 있다(타임아웃·일시 장애). 연속 streak 회차가 전부
0건일 때만 침묵으로 판정한다. 꺼진 출처는 counts에 아예 없으므로 대상이 아니다.

counts 는 수집 직후 건수다. 갱신이 멈춰 옛 글만 계속 돌려주는 피드는 매 회차
8건이라 여기에 안 잡힌다. 그래서 기간 필터(recent_only)를 지난 건수를 recent 로
같이 적고, 더 긴 창(stale_streak)으로 따로 본다. 글이 드문 출처(카카오 기술블로그,
Anthropic 뉴스)는 기간 안 글이 7일 동안 없던 적이 있어 3회차로 보면 늘 걸린다.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from news.core.common import ROOT, load_json
DEFAULT_PATH = os.path.join(ROOT, "data", "source_health.json")
KEEP = 30           # 보관할 회차 수 (하루 3회 → 열흘)
DEFAULT_STREAK = 3  # 연속 0건 판정 회차 수 (하루)
# 기간 내 0건 판정 회차 수 (9일). 2026-09-01~10-07 후보 로그에서 기간 안 글이
# 없던 최장 구간이 7일이었다(카카오 기술블로그·Anthropic 뉴스). KEEP 보다 길면
# 판정이 영영 안 된다.
DEFAULT_STALE_STREAK = 27


def load(path: str = DEFAULT_PATH) -> list[dict]:
    """record() 가 이 값 뒤에 이번 회차를 붙여 같은 경로에 다시 쓴다. 빈
    목록으로 돌려주면 30회차 이력이 1회로 줄고, silent() 의 이력 부족 조건
    때문에 그 뒤 최소 streak 회차 동안 침묵 판정 자체가 불가능해진다."""
    return load_json(path, [])


def record(counts: dict[str, int], when: str,
           path: str = DEFAULT_PATH, keep: int = KEEP,
           skip_days: dict[str, list[int]] | None = None,
           recent: dict[str, int] | None = None) -> list[dict]:
    """회차 결과를 뒤에 붙이고 최근 keep개만 남긴다. 갱신된 이력을 돌려준다.

    skip_days 는 출처가 발행을 쉬는 요일(0=월 … 6=일)이다 (feed-skip-days). 피드가 <skipDays>로
    직접 알려준 값만 들어온다.

    recent 는 기간 필터를 지난 출처별 건수다. counts 와 같은 키를 쓰고, 0건인
    출처도 빠짐없이 적는다. 이 파일을 읽는 다른 코드는 counts 만 보므로 키를 따로 둔다.
    """
    history = load(path)
    entry = {"at": when, "counts": dict(counts)}
    if recent is not None:
        entry["recent"] = dict(recent)
    if skip_days:
        entry["skip"] = {k: list(v) for k, v in skip_days.items() if v}
    history.append(entry)
    history = history[-keep:]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=1)
    return history


def _weekday(at: str) -> int | None:
    """회차 시각의 요일 — **UTC 기준**.

    at 은 수집 기계의 시각(KST)이다. 그대로 요일을 뽑으면 피드가 말한 요일과
    어긋난다. KST 월요일 00시는 UTC 일요일 15시라, arXiv 가 주말 껍데기를
    주는 그 회차를 월요일로 세어 휴재 예외가 빗나간다 — 하루 세 회차 중 둘이
    그렇다. <skipDays> 는 피드 자신의 발행 일정이므로 피드 쪽 시간대로 본다.
    """
    try:
        dt = datetime.fromisoformat(at)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        return dt.weekday()
    return dt.astimezone(timezone.utc).weekday()


def silent(history: list[dict], streak: int = DEFAULT_STREAK,
           key: str = "counts") -> list[str]:
    """마지막 streak 회차에 전부 등장하면서 전부 0건인 출처 이름 (정렬).

    출처가 <skipDays>로 쉰다고 밝힌 요일의 회차는 그 출처에 한해 세지 않는다.
    arXiv 는 주말에 <item> 이 없는 껍데기를 주므로, 그걸 모르면 매주 토·일에
    죽은 출처로 잡힌다. 쉬는 날을 빼고 나서 셀 회차가 없으면 판정하지 않는다.

    key="recent" 면 기간 필터 뒤 건수로 판정한다. recent 가 없는 옛 회차는
    그 출처가 등장하지 않은 회차와 같게 취급되어 판정에서 빠진다.
    """
    if streak <= 0 or len(history) < streak:
        return []
    names = set(history[-streak:][0].get(key, {}))
    for h in history[-streak:][1:]:
        names &= set(h.get(key, {}))

    # 휴재 요일은 회차가 아니라 출처의 성질이다. 회차별 값만 보면 두 군데서
    # 빗나간다 — 기능이 생기기 전 회차에는 아예 없고, 피드 요청이 실패한
    # 회차에도 안 남는다. 그 회차들이 전부 '쉬는 날이 아니다'로 세어져 거짓
    # 침묵을 만든다. 이력에서 가장 최근에 알려진 값을 그 출처에 쓴다.
    latest_skip: dict[str, list[int]] = {}
    for h in reversed(history):
        for n, days in (h.get("skip") or {}).items():
            if days and n not in latest_skip:
                latest_skip[n] = days

    out = []
    for n in names:
        # 휴재 요일 회차는 빼고, 남은 것 중 최근 streak개로 판정한다. 그만큼
        # 모이지 않았으면 아직 판정하지 않는다 — 한 회차 0건은 정상일 수 있다는
        # 원래 기준을 휴재 요일을 빼고도 지키려면 창을 뒤로 넓혀야 한다.
        judged = [h for h in history
                  if n in h.get(key, {})
                  and _weekday(h.get("at", "")) not in latest_skip.get(n, [])]
        judged = judged[-streak:]
        if len(judged) >= streak and all(h[key].get(n, 0) == 0 for h in judged):
            out.append(n)
    return sorted(out)


def stale(history: list[dict], streak: int = DEFAULT_STALE_STREAK) -> list[str]:
    """응답은 하는데 기간 안 글이 streak 회차 연속 0건인 출처 (정렬).

    마지막 회차에 수집 건수까지 0이면 여기서 빼고 silent() 에 맡긴다 — 같은
    출처가 두 번 알려지지 않게 하려는 것이다.
    """
    last = history[-1].get("counts", {}) if history else {}
    return [n for n in silent(history, streak, key="recent") if last.get(n, 0) > 0]


def health_keys(a: dict) -> list[str]:
    """기사 하나가 들어갈 건수 키. 수집기가 counts 에 쓰는 이름과 같아야 한다.

    Trendshift 기사는 source 가 github 이라 feed 로 가른다 (scrapers/trendshift.py).
    """
    src = a.get("source") or ""
    if src == "github" and a.get("feed") == "Trendshift":
        return ["trendshift"]
    keys = [src]
    if src in ("rss", "anthropic") and a.get("feed"):
        keys.append(f"{src}:{a['feed']}")
    elif src == "devto" and a.get("tag"):
        keys.append(f"devto:{a['tag']}")
    return keys


def count_by_source(articles: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for a in articles:
        for k in health_keys(a):
            out[k] = out.get(k, 0) + 1
    return out


# 기사 단위로 셀 수 있는 하위 키의 앞부분. geeknews:원문 처럼 기사 수가 아닌
# 건수는 기간 필터 뒤 값이 없으니 recent 에 넣지 않는다 — 넣으면 늘 0이라 거짓 알림이 된다.
# devto:태그 도 뺀다. 같은 글이 여러 태그에 걸리면 앞 태그 몫으로만 남아(devto.fetch),
# 뒤 태그는 수집 10건인데 기간 내 0건으로 보일 수 있다. 태그는 수집 0건(429)만 본다.
_PER_ARTICLE = ("rss", "anthropic")


def recent_counts(articles: list[dict], counts: dict[str, int]) -> dict[str, int]:
    """기간 필터를 지난 기사를 counts 와 같은 키로 센다. 0건인 출처도 적는다."""
    got = count_by_source(articles)
    return {k: got.get(k, 0) for k in counts
            if ":" not in k or k.split(":", 1)[0] in _PER_ARTICLE}
