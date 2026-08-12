#!/usr/bin/env python3
"""요약 품질 채점 — 모델·프롬프트를 바꿀 때 회귀를 잡는다 (add-summary-quality-eval).

  python scripts/eval_summary.py                    # 현재 설정으로 채점
  python scripts/eval_summary.py --model <모델명>    # 다른 모델로 채점
  python scripts/eval_summary.py --save-baseline    # 결과를 기준선으로 저장

LLM을 실제로 호출하므로 CI가 아니라 사람이 돌린다. 채점기 자체(news/core/quality.py)는
LLM 없이 CI에서 항상 검증된다.

기준선 대비 회귀가 있으면 exit 1. 온도가 0이 아니라 실행마다 결과가 다르므로
정확값이 아니라 허용 오차(기본 10%p)로 판정한다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import build  # noqa: E402
from news.core import quality  # noqa: E402

CORPUS = os.path.join(ROOT, "tests", "golden", "corpus.json")
BASELINE = os.path.join(ROOT, "tests", "golden", "baseline.json")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", help="비워두면 config.yaml / summarizer 기본값")
    ap.add_argument("--save-baseline", action="store_true")
    ap.add_argument("--tolerance", type=float, default=0.10)
    args = ap.parse_args()

    build.load_dotenv()
    from news.summarizer import summarize_all

    corpus = json.load(open(CORPUS, encoding="utf-8"))
    articles = [{**a, "url": f"golden://{i}"} for i, a in enumerate(corpus)]
    llm = build.load_config().get("llm", {})
    model = args.model or llm.get("model") or None

    out = summarize_all(articles, model=model,
                        pause=float(llm.get("pause_seconds", 4.0)),
                        max_calls=len(articles) * 3)
    result = quality.score(out)
    result["model"] = model or "(summarizer 기본값)"

    print(f"\n=== 채점: {result['model']} · {result['count']}건 ===")
    print(f"무결점 비율 {result['clean_rate']:.0%} · 제목 반복도(참고) {result['echo_mean']:.0%}")
    for code in quality.CHECKS:
        rate = result["pass_rate"][code]
        mark = "OK " if rate == 1.0 else "!! "
        print(f"  {mark}{code:14} {rate:.0%}")
    for code, titles in result["failures"].items():
        for t in titles:
            print(f"     - [{code}] {t}")

    if args.save_baseline:
        json.dump(result, open(BASELINE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\n기준선 저장: {BASELINE}")
        return 0

    if not os.path.exists(BASELINE):
        print("\n기준선이 없습니다. --save-baseline으로 먼저 만드세요.")
        return 0

    baseline = json.load(open(BASELINE, encoding="utf-8"))
    regressions = quality.compare(result, baseline, args.tolerance)
    if regressions:
        print(f"\n회귀 감지 (기준선: {baseline.get('model')}, 허용오차 {args.tolerance:.0%})")
        for r in regressions:
            print(f"  ✗ {r}")
        return 1
    print(f"\n회귀 없음 (기준선: {baseline.get('model')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
