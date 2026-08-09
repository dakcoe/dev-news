#!/usr/bin/env python3
"""아카이브 한자 잔존 기사 소급 정화 (fix-hanja-residual).

fix-hanja-leak 이전에 게시돼 한자가 박제된 기사를 찾아 LLM으로 재생성한다.
아카이브에 content가 보존돼 있어 요약 재료가 있다. 한자 없이 성공한 것만
교체하며(summarizer가 한자 응답을 수용하지 않으므로 성공 = 한자 없음 보장),
실패한 기사는 원문 유지 후 로그로 보고한다.

  python scripts/fix_hanja.py

교체 후에는 태그·인덱스·docs를 retag 플로우로 재생성한다
(ko_title/summary가 바뀌면 태그 매칭 결과도 달라질 수 있다).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from build import load_dotenv                          # noqa: E402
from news.core import archive                          # noqa: E402
from news.summarizer import HANJA_RE, summarize_all    # noqa: E402


def _dirty(a: dict) -> bool:
    joined = " ".join(filter(None, [a.get("ko_title"), a.get("summary"), a.get("why")]))
    return bool(HANJA_RE.search(joined))


def main() -> int:
    load_dotenv()
    total_fixed = total_dirty = 0

    for m in archive.months():
        path = os.path.join(archive.DIR, f"{m}.json")
        shard = archive._load_json(path)
        targets = [(i, a) for i, a in enumerate(shard) if _dirty(a)]
        if not targets:
            continue
        total_dirty += len(targets)
        print(f"[fix-hanja] {m}: 한자 잔존 {len(targets)}건 재생성 시도")

        # 기사당 최대 3회 호출이므로 예산은 3배로. pause는 TPM 여유용 기본값 유지.
        results = summarize_all([a for _, a in targets], max_calls=len(targets) * 3)

        for (i, _), r in zip(targets, results):
            if r.get("llm_done"):
                shard[i].update(ko_title=r["ko_title"], summary=r["summary"], why=r["why"])
                total_fixed += 1
            else:
                print(f"  · 실패(원문 유지): {shard[i]['title'][:50]}")
        archive._save_json(path, shard)

    print(f"[fix-hanja] {total_dirty}건 중 {total_fixed}건 정화")
    if total_fixed:
        import retag                                   # 같은 scripts/ 디렉터리
        retag.main()                                   # 재태깅 + 인덱스 + 렌더 + docs 동기화
    return 0


if __name__ == "__main__":
    sys.exit(main())
