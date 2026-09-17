#!/usr/bin/env python3
"""원격에 먼저 올라간 회차의 데이터를 이번 회차 결과에 합친다.

왜 필요한가. 커밋 단계가 `git pull --rebase -X theirs`로 충돌을 넘겼다. 그건
"내가 방금 만든 파일이 이긴다"는 뜻이라, 원격에 더 새로운 회차가 있으면 그 회차가
모은 기사와 seen 기록이 조용히 사라졌다. 게시 건수는 정상이라 열화 알림도 안 뛴다.

옛 SHA에서 Re-run을 누르면 확실히 재현된다. 며칠 전 스냅샷으로 build.py가 돌아
그 사이 쌓인 것을 모르는 채로 파일을 새로 쓰고, 그게 원격을 이긴다.

고치는 방향은 "누가 이기나"를 정하는 게 아니다. seen 기록과 기사 아카이브는
더하기만 하는 자료다. 겹치면 합집합이 맞다. 이 스크립트가 커밋 전에 우리 파일을
원격의 상위집합으로 만들어 두면, 그 뒤 rebase에서 우리가 이겨도 잃는 게 없다.

페이지·검색 인덱스는 파생물이라 합칠 필요가 없다. 합쳐진 아카이브로 다시 만든다.
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from news.core.dedup import normalize_url  # noqa: E402

REF = sys.argv[1] if len(sys.argv) > 1 else "origin/main"


def remote_json(path: str):
    """원격 ref의 파일을 읽는다. 그 ref에 없으면 None (새로 생긴 파일이다)."""
    try:
        raw = subprocess.run(["git", "show", f"{REF}:{path}"], cwd=ROOT,
                             capture_output=True, check=True).stdout
    except subprocess.CalledProcessError:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        print(f"[merge] {path} 원격본을 읽지 못했다 — 건너뛴다")
        return None


def local_json(path: str):
    full = os.path.join(ROOT, path)
    if not os.path.exists(full):
        return None
    with open(full, encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, obj, sort_keys: bool = False) -> None:
    """정본과 같은 형식으로 쓴다.

    형식이 다르면 25건을 되살리는 데 파일 전체가 새 덩어리로 쌓인다 — 회차마다
    커밋되는 양을 줄여 놓은 것을 이 경로가 그대로 되돌린다. archive는 indent=1,
    seen은 indent=1에 키 정렬이다.
    """
    full = os.path.join(ROOT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, sort_keys=sort_keys)


def merge_seen() -> int:
    """seen.json은 URL 집합이다. 형태가 dict든 list든 키를 합친다."""
    path = "data/seen.json"
    remote, local = remote_json(path), local_json(path)
    if remote is None or local is None:
        return 0
    if isinstance(remote, dict) and isinstance(local, dict):
        added = [k for k in remote if k not in local]
        merged = {**remote, **local}          # 같은 키는 이번 회차 값을 남긴다
    elif isinstance(remote, list) and isinstance(local, list):
        seen = set(map(str, local))
        added = [k for k in remote if str(k) not in seen]
        merged = local + added
    else:
        print(f"[merge] {path} 형태가 달라 합치지 않는다")
        return 0
    if added:
        write_json(path, merged, sort_keys=True)
    return len(added)


def _insert_by_batch(local: list[dict], missing: list[dict]) -> list[dict]:
    """있는 줄은 그대로 두고 빠진 것만 batch 위치에 끼운다.

    ⚠️ 있는 항목을 손대지 않는 것이 이 스크립트의 제1원칙이다. 원격을 뼈대로
    삼아 다시 쓰면 줄 수는 덜 바뀌지만, 같은 기사의 다른 판본으로 교체되면서
    upvotes·출처 같은 값이 조용히 달라진다. 복구가 아니라 변조다.

    전체를 다시 정렬하지도 않는다 — 회차 안의 순서가 바뀌어 25건 되살리는 데
    8천 줄이 다시 쓰였다. 파일은 최신이 위로 쌓인다.
    """
    out, rest = [], sorted(missing, key=lambda a: a.get("batch") or "", reverse=True)
    for item in local:
        b = item.get("batch") or ""
        while rest and (rest[0].get("batch") or "") > b:
            out.append(rest.pop(0))
        out.append(item)
    return out + rest


def merge_shards() -> int:
    """월별 기사 샤드. 같은 기사인지는 url 과 회차로 가린다."""
    shard_dir = os.path.join(ROOT, "docs", "data", "articles")
    names = set(os.listdir(shard_dir)) if os.path.isdir(shard_dir) else set()
    try:
        out = subprocess.run(["git", "ls-tree", "--name-only", f"{REF}:docs/data/articles"],
                             cwd=ROOT, capture_output=True, check=True)
        names |= set(out.stdout.decode().split())
    except subprocess.CalledProcessError:
        pass

    total = 0
    for name in sorted(n for n in names if n.endswith(".json")):
        path = f"docs/data/articles/{name}"
        remote, local = remote_json(path), local_json(path)
        if remote is None:
            continue
        local = local or []
        # 같은 기사인지는 archive·seen·중복제거와 같은 규칙으로 가린다. 주소를
        # 그대로 비교하면 끝 슬래시 하나 차이로 같은 기사가 두 번 들어간다.
        # 회차까지 같아야 같은 항목이다 — 다시 트렌딩에 오른 저장소는 같은 URL 로
        # 다른 회차에 한 번 더 실린다.
        key = lambda a: (normalize_url(a.get("url")) or a.get("url"), a.get("batch") or "")
        have = {key(a) for a in local}
        missing = [a for a in remote if key(a) not in have]
        if missing:
            # 있는 줄은 건드리지 않고 빠진 것만 제자리에 끼운다. 전체를 다시
            # 정렬하면 회차 안의 순서가 바뀌어 파일이 통째로 새로 쌓인다 —
            # 25건 되살리는 데 8천 줄이 다시 쓰였다. 파일은 최신이 위다.
            merged = _insert_by_batch(local, missing)
            write_json(path, merged)
            print(f"[merge] {path} — 원격에만 있던 {len(missing)}건을 되살렸다")
            total += len(missing)
    return total


def rebuild_derived() -> None:
    """합쳐진 아카이브로 검색 인덱스와 페이지를 다시 만든다."""
    from datetime import datetime

    from build import KST, load_config
    from news.core import archive
    from news.render import render, write_seo_files

    cfg = load_config()
    all_articles = archive.load_all()
    archive.write_search_index(all_articles)

    batches = [a["batch"] for a in all_articles if a.get("batch")]
    now = datetime.fromisoformat(max(batches)) if batches else datetime.now(KST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=KST)

    display = archive.recent(all_articles, cfg.get("scraper", {}).get("keep_days", 30))
    out = os.path.join(ROOT, "docs", "index.html")
    render(display, out, collected=now, enabled=cfg.get("sources", {}), about=cfg.get("about"),
           ads=cfg.get("ads"))
    write_seo_files(os.path.join(ROOT, "docs"), now)


def main() -> int:
    seen_added = merge_seen()
    shard_added = merge_shards()
    if seen_added or shard_added:
        print(f"[merge] 원격에서 되살린 것 — seen {seen_added}건 · 기사 {shard_added}건")
        rebuild_derived()
        print("[merge] 검색 인덱스·페이지를 다시 만들었다")
    else:
        print("[merge] 원격에만 있는 데이터 없음 — 합칠 것이 없다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
