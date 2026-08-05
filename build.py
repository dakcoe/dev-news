#!/usr/bin/env python3
"""개발·AI 뉴스 페이지 빌더.

  python build.py            # 수집 → 요약 → docs/index.html 생성
  python build.py --demo     # 네트워크·Gemini 없이 sample.json으로 렌더만 (레이아웃 확인용)
  python build.py --no-ai    # 수집은 하되 Gemini 요약은 건너뜀 (원문 설명 그대로 사용)

환경변수
  LLM_PROVIDER   groq(기본) / openrouter / gemini
  GROQ_API_KEY   공급자에 맞는 키 하나 (OPENROUTER_API_KEY, GEMINI_API_KEY)
  LLM_MODEL      모델을 직접 지정하고 싶을 때만
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

import yaml

from news.core import archive
from news.core import seen as seen_db
from news.core.enrich import enrich
from news.core.scorer import score_and_categorize
from news.render import render
from news.scrapers import anthropic, devto, geeknews, github, hackernews, lobsters, reddit, rss

ROOT = os.path.dirname(os.path.abspath(__file__))
KST = timezone(timedelta(hours=9))
TRUSTED = {"github", "devto", "geeknews", "rss", "anthropic"}   # 키워드 필터를 적용하지 않는 출처


def load_dotenv(path: str | None = None) -> None:
    """폴더에 .env가 있으면 읽어서 환경변수로 넣는다.

    이미 설정된 환경변수는 덮어쓰지 않는다 (GitHub Actions의 Secrets가 우선).
    KEY=value 형식, # 로 시작하는 줄은 주석, 따옴표는 벗겨낸다.
    """
    path = path or os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        return
    loaded = []
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
                loaded.append(key)
    if loaded:
        print(f"[.env] {', '.join(loaded)} 불러옴")


def load_config() -> dict:
    with open(os.path.join(ROOT, "config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_scrapers(cfg: dict) -> list[dict]:
    s = cfg.get("scraper", {})
    src = cfg.get("sources", {})
    tasks = {}
    if src.get("hackernews", True):
        tasks["hackernews"] = lambda: hackernews.fetch(limit=s.get("hn_limit", 60))
    if src.get("github", True):
        tasks["github"] = lambda: github.fetch()
    if src.get("lobsters", True):
        tasks["lobsters"] = lambda: lobsters.fetch(limit=s.get("per_source", 30))
    if src.get("devto", True):
        tasks["devto"] = lambda: devto.fetch(tags=s.get("devto_tags"))
    if src.get("reddit", False):
        tasks["reddit"] = lambda: reddit.fetch(subreddits=s.get("subreddits"))
    if src.get("geeknews", True):
        tasks["geeknews"] = lambda: geeknews.fetch(limit=s.get("per_source", 30))
    if src.get("rss", True):
        tasks["rss"] = lambda: rss.fetch(cfg.get("feeds"), per_feed=s.get("per_feed", 8))
    if src.get("anthropic", True):
        tasks["anthropic"] = lambda: anthropic.fetch(limit=s.get("per_feed", 8))

    articles: list[dict] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(fn): name for name, fn in tasks.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                got = future.result()
                print(f"[{name}] {len(got)}개 수집")
                articles.extend(got)
            except Exception as e:
                print(f"[{name}] 실패: {e}")
    return articles


def keyword_filter(articles: list[dict], keywords: list[str]) -> list[dict]:
    if not keywords:
        return articles
    lowered = [k.lower() for k in keywords]
    kept, dropped = [], 0
    for a in articles:
        if a["source"] in TRUSTED:
            kept.append(a)
            continue
        text = (a.get("title", "") + " " + a.get("description", "")).lower()
        if any(k in text for k in lowered):
            kept.append(a)
        else:
            dropped += 1
    if dropped:
        print(f"[필터] 키워드 불일치 {dropped}건 제외")
    return kept


def recent_only(articles: list[dict], hours: int, long_sources: dict[str, int] | None = None) -> list[dict]:
    """최근 N시간 내 발행분만 남긴다.

    long_sources에 적힌 출처는 더 긴 창을 쓴다. 공식 블로그처럼 글이 드문 곳은
    48시간으로 자르면 아예 못 보고 지나가기 때문이다. (중복은 seen.json이 막는다)
    """
    long_sources = long_sources or {}
    now = datetime.now(timezone.utc).timestamp()
    kept = []
    for a in articles:
        ts = a.get("published_at")
        if ts is None:                      # 게시 시각을 모르는 출처(GitHub 트렌딩 등)는 통과
            kept.append(a)
            continue
        window = long_sources.get(a.get("source"), hours)
        try:
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
            if float(ts) >= now - window * 3600:
                kept.append(a)
        except Exception:
            kept.append(a)
    print(f"[필터] 최근 {hours}시간 내 {len(kept)}건")
    return kept


def adjust_scores(articles: list[dict], cfg: dict) -> list[dict]:
    """출처별 기본점수·가중치를 적용해 서로 다른 저울을 맞춘다.

    GitHub의 '오늘 받은 스타 2,800'과 HN의 '700점'과 블로그의 '0점'은
    그대로 두면 비교가 안 된다. base는 점수 개념이 없는 출처의 바닥값,
    weight는 과대·과소평가되는 출처를 눌러주거나 올려주는 배수다.
    """
    base = cfg.get("source_base", {})
    weight = cfg.get("source_weight", {})
    for a in articles:
        src = a.get("source", "")
        a["score"] = (a.get("score", 0) + base.get(src, 0)) * weight.get(src, 1.0)
    articles.sort(key=lambda x: x.get("score", 0), reverse=True)
    return articles


def pick(articles: list[dict], top_n: int, per_source: int,
         quota: dict[str, int] | None = None) -> list[dict]:
    """점수순 목록에서 최종 선별.

    1단계 — source_quota에 적힌 출처는 그 개수를 먼저 확보한다(점수와 무관하게 자리 보장).
    2단계 — 남은 자리를 전체 점수순으로 채우되 출처당 상한을 지킨다.
    """
    quota = quota or {}
    counts: dict[str, int] = defaultdict(int)
    picked: list[dict] = []
    taken: set[int] = set()

    for src, n in quota.items():
        for i, a in enumerate(articles):
            if counts[src] >= n or len(picked) >= top_n:
                break
            if i in taken or a["source"] != src:
                continue
            taken.add(i)
            counts[src] += 1
            picked.append(a)
        if counts[src] < n:
            print(f"[선별] {src} 보장 {n}건 중 {counts[src]}건만 확보 (후보 부족)")

    for i, a in enumerate(articles):
        if len(picked) >= top_n:
            break
        if i in taken:
            continue
        cap = max(per_source, quota.get(a["source"], 0))
        if counts[a["source"]] >= cap:
            continue
        taken.add(i)
        counts[a["source"]] += 1
        picked.append(a)

    picked.sort(key=lambda x: x.get("score", 0), reverse=True)
    print("[선별] " + " · ".join(f"{k} {v}" for k, v in sorted(counts.items()) if v))
    return picked


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="sample.json으로 렌더만 수행")
    ap.add_argument("--no-ai", action="store_true", help="Gemini 요약 건너뛰기")
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "index.html"))
    args = ap.parse_args()

    load_dotenv()

    if args.demo:
        with open(os.path.join(ROOT, "sample.json"), encoding="utf-8") as f:
            render(json.load(f), args.out, enabled=load_config().get("sources", {}))
        return 0

    cfg = load_config()
    sc = cfg.get("scraper", {})

    articles = run_scrapers(cfg)
    print(f"전체 수집 {len(articles)}건")
    articles = keyword_filter(articles, cfg.get("keywords", []))
    articles = recent_only(articles, sc.get("window_hours", 48), cfg.get("long_window", {}))
    # 자르지 않고 전부 점수화한 뒤 출처 보정을 적용한다 (보정 전에 잘리면 의미가 없다)
    articles = score_and_categorize(articles, top_n=len(articles))
    articles = adjust_scores(articles, cfg)
    articles = seen_db.filter_unseen(articles)
    articles = pick(articles, sc.get("top_n", 20), sc.get("per_source", 5),
                    quota=cfg.get("source_quota", {}))

    if not articles:
        print("새 기사가 없습니다. 기존 페이지를 유지합니다.")
        return 0
    print(f"이번 회차 {len(articles)}건 선별")

    articles = enrich(articles)

    if args.no_ai:
        for a in articles:
            a.setdefault("summary", a.get("description", ""))
    else:
        from news.summarizer import summarize_all
        articles = summarize_all(articles)

    now = datetime.now(KST)
    all_articles = archive.append(
        articles, now,
        keep_days=sc.get("keep_days", 30),
        max_items=sc.get("max_items", 300),
    )
    render(all_articles, args.out, collected=now, enabled=cfg.get("sources", {}))
    seen_db.mark_seen(articles)
    return 0


if __name__ == "__main__":
    sys.exit(main())
