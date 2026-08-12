#!/usr/bin/env python3
"""기존 샤드에서 수집 원문(content)을 제거하는 일회성 정리 (drop-unused-content).

archive.append()가 앞으로는 content를 저장하지 않지만, 이미 쌓인 것은 남아 있다.
이번 달 샤드는 가변이라 "지난 달 샤드 불변" 원칙에 걸리지 않는다.

  python scripts/purge_content.py           # 미리보기
  python scripts/purge_content.py --apply   # 실제 적용
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from news.core.archive import DIR, DROP_FIELDS, _shard_path, months  # noqa: E402


def main() -> int:
    apply = "--apply" in sys.argv
    total_before = total_after = 0

    for month in months():
        path = _shard_path(month, DIR)
        before = os.path.getsize(path)
        with open(path, encoding="utf-8") as f:
            rows = json.load(f)

        hit = sum(1 for a in rows if any(k in a for k in DROP_FIELDS))
        cleaned = [{k: v for k, v in a.items() if k not in DROP_FIELDS} for a in rows]
        blob = json.dumps(cleaned, ensure_ascii=False, indent=1)
        after = len(blob.encode("utf-8"))

        total_before += before
        total_after += after
        pct = (before - after) * 100 // before if before else 0
        print(f"  {month}.json  {before:>10,}B → {after:>10,}B  ({pct}%↓, {hit}/{len(rows)}건)")

        if apply:
            with open(path, "w", encoding="utf-8") as f:
                f.write(blob)

    if total_before:
        pct = (total_before - total_after) * 100 // total_before
        print(f"\n합계 {total_before:,}B → {total_after:,}B ({pct}% 감소)")
    print("적용됨" if apply else "\n미리보기입니다. 적용하려면 --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
