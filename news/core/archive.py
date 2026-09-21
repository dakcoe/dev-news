"""수집한 기사를 월별 샤드에 무한 누적한다 (SPEC Phase 2.1~2.2).

원칙: 저장과 표시를 분리한다. 저장은 docs/data/articles/YYYY-MM.json에 무제한 누적하고,
표시 범위(index.html에 굽는 기간)는 빌드가 recent()로 골라낸다.

단일 파일 무한 성장은 git 히스토리를 부풀리고 GitHub의 파일 100MB push 제한에
걸린다. 지난 달 샤드는 이후 절대 수정하지 않으므로(불변) git이 한 번만 저장하고,
브라우저 캐시 적중률도 100%가 된다. 매일 수정되는 파일은 이번 달 샤드 하나뿐이다.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

from news.core.common import ROOT, DataUnreadable, load_json  # noqa: E402  (경로 상수 재노출)

# 옛 이름. archive 만 쓰던 예외를 공용으로 올렸다.
ShardUnreadable = DataUnreadable
from news.core.dedup import normalize_url
# 정본은 docs/ 아래다. GitHub Pages가 서빙하는 곳이라 방문자가 여기서 받아 가고,
# 빌드도 여기서 읽는다. 예전에는 data/에 두고 docs/로 복사해서 같은 내용이 두 벌
# 커밋됐다 — 회차마다 1.6MB가 두 번씩 새 덩어리로 쌓였다.
DIR = os.path.join(ROOT, "docs", "data", "articles")
LEGACY_PATH = os.path.join(ROOT, "data", "articles.json")
INDEX_PATH = os.path.join(ROOT, "docs", "data", "search-index.json")


def _month(batch_iso: str) -> str:
    return (batch_iso or "")[:7] or datetime.now(timezone.utc).strftime("%Y-%m")


def _shard_path(month: str, base_dir: str = DIR) -> str:
    return os.path.join(base_dir, f"{month}.json")


def _load_json(path: str) -> list:
    """append() 는 `stamped + _load_json(...)` 를 같은 경로에 바로 저장한다.
    읽기 실패가 빈 목록이 되면 그달 기사가 새 기사만 남기고 사라진다."""
    return load_json(path, [])


def _save_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def months(base_dir: str = DIR) -> list[str]:
    if not os.path.isdir(base_dir):
        return []
    return sorted(fn[:-5] for fn in os.listdir(base_dir) if fn.endswith(".json"))


def load_all(base_dir: str = DIR) -> list[dict]:
    out: list[dict] = []
    for m in reversed(months(base_dir)):
        out.extend(_load_json(_shard_path(m, base_dir)))
    out.sort(key=lambda a: a.get("batch", ""), reverse=True)
    return out


def migrate_legacy(legacy_path: str = LEGACY_PATH, base_dir: str = DIR) -> None:
    """단일 articles.json → 월별 샤드 분리. 멱등: 파일이 없으면 아무것도 안 한다."""
    if not os.path.exists(legacy_path):
        return
    legacy = _load_json(legacy_path)
    by_month: dict[str, list[dict]] = {}
    for a in legacy:
        by_month.setdefault(_month(a.get("batch", "")), []).append(a)
    for m, items in by_month.items():
        shard = _load_json(_shard_path(m, base_dir))
        known = {x.get("url") for x in shard}
        merged = [a for a in items if a.get("url") not in known] + shard
        merged.sort(key=lambda a: a.get("batch", ""), reverse=True)
        _save_json(_shard_path(m, base_dir), merged)
    os.remove(legacy_path)
    print(f"[archive] 마이그레이션: {len(legacy)}건 → 월별 샤드 {len(by_month)}개, articles.json 제거")


# 요약 생성에만 쓰이고 화면에는 나오지 않는 필드 — 저장하지 않는다.
# content(수집 원문 3000자)는 샤드 용량의 66%를 차지했고, 남의 API 토큰이
# 섞여 들어와 push가 거부되는 사고의 통로이기도 했다 (fix-secret-push-block).
# 요약 파이프라인은 enrich→summarizer 구간에서 이미 다 쓰고 넘어온다.
DROP_FIELDS = ("content",)


def append(new_items: list[dict], batch: datetime, base_dir: str = DIR) -> list[dict]:
    """새 기사에 수집 회차를 찍어 이번 달 샤드 앞에 붙인다. 삭제·상한 없음."""
    # 같은 기사인지는 seen·중복제거와 같은 규칙으로 가린다. 주소 문자열을 그대로
    # 비교하면 끝 슬래시 하나 차이로 같은 기사가 두 번 쌓인다.
    # 주소별로 가장 최근 회차를 들고 있는다. resurfaced 기사를 받아들일지
    # 판단하려면 "언제 마지막으로 실렸는가"를 알아야 한다.
    latest: dict[str, str] = {}
    for a in load_all(base_dir):
        key = normalize_url(a.get("url")) or a.get("url")
        at = a.get("batch") or ""
        if at > latest.get(key, ""):
            latest[key] = at

    def keep(a: dict) -> bool:
        key = normalize_url(a.get("url")) or a.get("url")
        prev = latest.get(key)
        if prev is None:
            return True
        # seen 이 "기간이 지나 다시 실을 만하다"고 판단해 통과시킨 기사다
        # (seen.filter_unseen). 주소가 같다는 이유로 버리면 요약을 새로 만들어
        # 놓고 저장하지 않게 된다 — 다시 트렌딩이 화면에 안 뜨고 LLM 호출만
        # 버려진다.
        #
        # 다만 무조건 받으면 중복 방지가 통째로 풀린다. 저장 뒤 렌더나 푸시가
        # 실패하면 seen 만 남고 아카이브는 롤백되지 않아, 다음 회차에 같은
        # 기사가 또 쌓인다. seen 이 쓰는 기준을 그대로 적용한다 — 마지막으로
        # 실린 회차가 resurfaced(지난 게시일)보다 뒤면 이미 이번 재등장으로
        # 실린 것이므로 받지 않는다.
        return bool(a.get("resurfaced")) and prev[:10] <= a["resurfaced"]

    stamped = [{**{k: v for k, v in a.items() if k not in DROP_FIELDS},
                "batch": batch.isoformat(),
                "batch_label": f"{batch.month}월 {batch.day}일 {batch:%H:%M}"}
               for a in new_items if keep(a)]

    m = _month(batch.isoformat())
    shard = stamped + _load_json(_shard_path(m, base_dir))
    _save_json(_shard_path(m, base_dir), shard)

    merged = load_all(base_dir)
    print(f"[archive] 신규 {len(stamped)}건 추가 · 전체 누적 {len(merged)}건 (샤드 {len(months(base_dir))}개)")
    return merged


def recent(articles: list[dict], days: int) -> list[dict]:
    """표시 계층: 최근 N일 회차만 남긴다. days=0이면 전체."""
    if not days:
        return articles
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()
    kept = []
    for a in articles:
        try:
            ts = datetime.fromisoformat(a["batch"]).timestamp()
        except Exception:
            ts = cutoff + 1
        if ts >= cutoff:
            kept.append(a)
    return kept


def _index_entry(a: dict) -> dict:
    return {"t": a.get("ko_title") or a.get("title", ""),
            "u": a.get("url", ""),
            "m": _month(a.get("batch", "")),
            "s": a.get("source", ""),
            "g": a.get("tags", []),
            "d": (a.get("batch", "") or "")[:10]}


def write_search_index(articles: list[dict], path: str = INDEX_PATH) -> None:
    """검색용 경량 색인 (기사당 100~200바이트). 기사 샤드와 같이 월별로 나눈다.

    한 파일에 전부 담으면 회차마다 그 파일 전체가 새로 쌓인다 — 6주에 564KB였고
    1년이면 5MB짜리가 하루 세 번씩 통째로 커밋된다. 월별로 나누면 이번 달 것만
    바뀌고 지난 달 것은 그대로 있다. 기사 샤드가 이미 쓰는 방식이다.

    path에는 어느 달이 있는지만 적는다. 화면은 그걸 읽고 달별 파일을 받아 붙인다.
    """
    by_month: dict[str, list[dict]] = {}
    for a in articles:
        e = _index_entry(a)
        by_month.setdefault(e["m"] or "unknown", []).append(e)

    base = os.path.dirname(path)
    os.makedirs(base, exist_ok=True)
    for m, rows in by_month.items():
        _save_json(os.path.join(base, f"search-index-{m}.json"), rows)

    _save_json(path, {"months": sorted(by_month)})
    print(f"[index] 검색 인덱스 {sum(map(len, by_month.values()))}건 · "
          f"{len(by_month)}개 달로 나눔")
