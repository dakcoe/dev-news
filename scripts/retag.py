#!/usr/bin/env python3
"""소급 태깅 스크립트 (SPEC 1B — add-article-tags).

기존 아카이브 전 기사에 닫힌 어휘 태그를 다시 부여하고, 검색 인덱스와
docs/(Pages 서빙 사본, index.html)를 재생성한다. 수집·LLM 호출 없음.

  python scripts/retag.py

태거는 규칙 기반이라 결정적이다 — news/core/tags.py의 어휘를 고친 뒤
이 스크립트를 재실행하면 전체 코퍼스가 새 어휘로 재태깅된다.
"지난 달 샤드 불변" 원칙의 유일한 예외가 이 소급 태깅이다 (SPEC 1B가 명시한 절차).
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from build import load_config, sync_docs_data          # noqa: E402
from news.core import archive                          # noqa: E402
from news.core.tags import tag_all                     # noqa: E402
from news.render import render                         # noqa: E402

KST = timezone(timedelta(hours=9))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    total = 0
    for m in archive.months():
        path = os.path.join(archive.DIR, f"{m}.json")
        shard = archive._load_json(path)
        tag_all(shard)
        archive._save_json(path, shard)
        total += len(shard)
        print(f"[retag] {m}: {len(shard)}건 태깅")

    all_articles = archive.load_all()
    archive.write_search_index(all_articles)

    cfg = load_config()
    display = archive.recent(all_articles, cfg.get("scraper", {}).get("keep_days", 30))
    render(display, os.path.join(ROOT, "docs", "index.html"),
           collected=datetime.now(KST), enabled=cfg.get("sources", {}))
    sync_docs_data()
    print(f"[retag] 완료: 총 {total}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
