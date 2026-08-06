"""수집한 기사를 월별 샤드에 무한 누적한다 (SPEC Phase 2.1~2.2).

원칙: 저장과 표시를 분리한다. 저장은 data/articles/YYYY-MM.json에 무제한 누적하고,
표시 범위(index.html에 굽는 기간)는 빌드가 recent()로 골라낸다.

단일 파일 무한 성장은 git 히스토리를 부풀리고 GitHub의 파일 100MB push 제한에
걸린다. 지난 달 샤드는 이후 절대 수정하지 않으므로(불변) git이 한 번만 저장하고,
브라우저 캐시 적중률도 100%가 된다. 매일 수정되는 파일은 이번 달 샤드 하나뿐이다.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DIR = os.path.join(ROOT, "data", "articles")
LEGACY_PATH = os.path.join(ROOT, "data", "articles.json")
INDEX_PATH = os.path.join(ROOT, "data", "search-index.json")


def _month(batch_iso: str) -> str:
    return (batch_iso or "")[:7] or datetime.now(timezone.utc).strftime("%Y-%m")


def _shard_path(month: str, base_dir: str = DIR) -> str:
    return os.path.join(base_dir, f"{month}.json")


def _load_json(path: str) -> list:
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"[archive] 읽기 실패({path}: {e}) — 빈 목록으로 처리")
        return []


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


def append(new_items: list[dict], batch: datetime, base_dir: str = DIR) -> list[dict]:
    """새 기사에 수집 회차를 찍어 이번 달 샤드 앞에 붙인다. 삭제·상한 없음."""
    known = {a.get("url") for a in load_all(base_dir)}
    stamped = [{**a, "batch": batch.isoformat(),
                "batch_label": f"{batch.month}월 {batch.day}일 {batch:%H:%M}"}
               for a in new_items if a.get("url") not in known]

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


def write_search_index(articles: list[dict], path: str = INDEX_PATH) -> None:
    """전체 게시 기사의 경량 색인 (기사당 100~200바이트). 빌드마다 재생성."""
    idx = [{"t": a.get("ko_title") or a.get("title", ""),
            "u": a.get("url", ""),
            "m": _month(a.get("batch", "")),
            "s": a.get("source", ""),
            "d": (a.get("batch", "") or "")[:10]}
           for a in articles]
    _save_json(path, idx)
    print(f"[index] 검색 인덱스 {len(idx)}건 재생성")
