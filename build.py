#!/usr/bin/env python3
"""개발·AI 뉴스 페이지 빌더.

  python build.py            # 수집 → 요약 → docs/index.html 생성
  python build.py --demo     # 네트워크·LLM 없이 sample.json으로 렌더만 (레이아웃 확인용)
  python build.py --no-ai    # 수집은 하되 LLM 요약은 건너뜀 (원문 설명 그대로 사용)

환경변수
  LLM_PROVIDER   groq(기본) — Groq 전용, 새 공급자 추가 금지 (SPEC 불변 제약)
  GROQ_API_KEY   Groq API 키
  LLM_MODEL      모델을 직접 지정하고 싶을 때만
  GITHUB_TOKEN   있으면 GitHub API 한도가 시간당 60→1,000회+ (Actions는 자동 제공)

깔때기 (SPEC 1.2): 넓은 수집 → 중복 제거 + candidates 로그 → 보조 점수 top_n 선별
→ 최종 선별분만 본문·썸네일·요약. 파이프라인 수준의 차단 필터는 두지 않는다 —
무엇을 보고 숨길지는 열람 단계(클라이언트 검색·필터)가 담당한다 (SPEC 1.1).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import yaml

from news import apis_catalog
from news.core import archive, candidates
from news.core import seen as seen_db
from news.core.dedup import merge_duplicates
from news.core.filters import (
    drop_dead_links,
    drop_irrelevant,
    keyword_filter,
    page_eligible,
    recent_only,
)
from news.core.select import adjust_scores, pick
from news.core.enrich import enrich
from news.core.redact import redact_articles
from news.core.scorer import score_and_categorize
from news.core.tags import tag_all
from news.render import render
from news.scrapers import anthropic, devto, geeknews, github, hackernews, lobsters, reddit, rss

ROOT = os.path.dirname(os.path.abspath(__file__))
from news.core.common import KST  # noqa: E402  (상수 재노출)
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


def apply_star_delta(articles: list[dict], today: str) -> dict[str, dict]:
    """GitHub 아이템의 지표를 절대 스타에서 전일 대비 증가량(Δ)으로 교체 (SPEC 1.5).

    candidates 샤드의 어제 스냅샷과 API의 현재 스타 수로 Δ를 계산한다.
    첫 등장(어제 데이터 없음)은 trending의 "stars today"(upvotes)를 그대로 쓴다.
    반환: url → GitHub API 메타 (candidates 로그에 재사용).
    """
    gh_items = [a for a in articles if a.get("source") == "github"]
    meta_map: dict[str, dict] = {}
    for a in gh_items:
        meta = candidates.github_meta(a["url"])
        meta_map[a["url"]] = meta
        prev = candidates.previous_stars(a["url"], before_date=today)
        if meta.get("stars") is not None and prev is not None:
            delta = max(meta["stars"] - prev, 0)
        else:
            delta = a.get("upvotes", 0)        # 첫 등장 — trending의 stars today
        a["upvotes"] = delta
        a["delta_stars"] = delta
    if gh_items:
        print(f"[Δ] GitHub {len(gh_items)}건 스타 증가량 적용")
    return meta_map


def emit_actions_output(published: int, min_published: int) -> bool:
    """게시 결과를 Actions 출력으로 내보낸다. 반환값은 '열화'로 판정했는지 여부.

    실패 알림(`if: failure()`)은 exit 1일 때만 뛴다. 그런데 이 파이프라인엔 성공으로
    끝나는 열화 경로가 있다 — 새 기사 없음, 요약 한도로 일부만 게시(SPEC 1.6),
    변경 없어 커밋 생략. "매일 도는데 조용히 3건씩만 올라오는" 상태를 잡으려면
    건수 자체를 신호로 내보내야 한다.

    임계 비교를 셸에서 하면 config.yaml을 bash로 파싱해야 하고 테스트도 못 한다.
    그래서 판정은 여기서 하고 워크플로는 플래그만 본다.
    로컬 실행(GITHUB_OUTPUT 없음)에서는 아무것도 하지 않는다.
    """
    degraded = published < min_published
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"published={published}\n")
            f.write(f"degraded={'true' if degraded else 'false'}\n")
    if degraded:
        print(f"[알림] 게시 {published}건 — 임계 {min_published}건 미만이라 열화로 보고합니다")
    return degraded


def sync_docs_data() -> None:
    """아카이브 검색용 데이터를 docs/로 복사 (SPEC 2.4).

    GitHub Pages는 /docs 폴더만 서빙하므로 data/를 직접 fetch할 수 없다.
    지난 달 샤드는 불변이라 복사해도 내용이 같으면 git 변경이 생기지 않는다.
    """
    dst_dir = os.path.join(ROOT, "docs", "data", "articles")
    os.makedirs(dst_dir, exist_ok=True)
    for m in archive.months():
        shutil.copyfile(os.path.join(archive.DIR, f"{m}.json"),
                        os.path.join(dst_dir, f"{m}.json"))
    if os.path.exists(archive.INDEX_PATH):
        shutil.copyfile(archive.INDEX_PATH,
                        os.path.join(ROOT, "docs", "data", "search-index.json"))

def _gate_settings(cfg: dict) -> tuple[int, bool, int, int | None]:
    """설정에서 파생되는 선별 값들. 여러 단계가 같은 값을 봐야 해서 한곳에 둔다."""
    sc = cfg.get("scraper", {})
    top_n = sc.get("top_n", 20)
    gate_on = bool(sc.get("relevance_gate", False))
    # 게이트가 꺼져 있으면 여유분도 0 — 동작이 도입 전과 완전히 같아진다
    overpick = sc.get("overpick", 5) if gate_on else 0
    return top_n, gate_on, overpick, sc.get("per_feed_page")


def collect_candidates(cfg: dict) -> list[dict]:
    """수집 → 필터 → 중복 제거. 깔때기의 넓은 쪽 (SPEC 1.2)."""
    sc = cfg.get("scraper", {})
    raw = run_scrapers(cfg)
    articles = keyword_filter(raw, cfg.get("keywords", []), cfg.get("block_keywords"))
    articles = recent_only(articles, sc.get("window_hours", 48), cfg.get("long_window", {}))
    articles = merge_duplicates(articles)
    # 남의 글에 박힌 토큰이 candidates 로그·아카이브에 실려 push되면 GitHub Push
    # Protection이 push를 거부해 회차 전체가 죽는다 (run 31510062957)
    articles = redact_articles(articles, "수집")
    print(f"[깔때기] 후보 {len(raw)}건 → 필터·중복 제거 후 {len(articles)}건")
    return articles


def select_articles(articles: list[dict], cfg: dict, now, today: str) -> list[dict]:
    """점수 → 미소개분 → 예약석·상한 적용. 판정 로그도 여기서 남긴다 (SPEC 1.4)."""
    sc = cfg.get("scraper", {})
    top_n, _, overpick, per_feed_page = _gate_settings(cfg)

    gh_meta_map = apply_star_delta(articles, today)
    articles = score_and_categorize(articles, top_n=len(articles))
    articles = adjust_scores(articles, cfg)

    fresh = seen_db.filter_unseen(page_eligible(articles))
    picked = pick(fresh, top_n + overpick, sc.get("per_source", 5),
                  quota=cfg.get("source_quota", {}), per_feed_page=per_feed_page)
    print(f"[깔때기] 미소개 {len(fresh)}건 → 최종 선별 {len(picked)}건 "
          f"(목표 {top_n} + 여유 {overpick})")

    candidates.log(articles, {a["url"] for a in picked}, now, gh_meta_map)
    return picked


def prepare_published(picked: list[dict], cfg: dict,
                      no_ai: bool) -> tuple[list[dict], list[dict], list[dict]]:
    """본문·요약·태깅. (게재분, 무관 제외분, 죽은 링크 제외분)을 돌려준다."""
    sc = cfg.get("scraper", {})
    top_n, gate_on, _, per_feed_page = _gate_settings(cfg)

    # 본문은 여기서 처음 들어온다. 요약 요청 전에 지워야 남의 토큰이 LLM
    # 공급자에게 전송되는 것까지 막힌다.
    picked = redact_articles(enrich(picked), "본문")
    # 죽은 링크는 요약 전에 뺀다 — LLM 호출을 쓰지 않게 된다
    picked, dead_links = drop_dead_links(picked)

    if no_ai:
        for a in picked:
            a.setdefault("summary", a.get("description", ""))
            a["llm_done"] = True
    else:
        from news.summarizer import summarize_all
        llm_cfg = cfg.get("llm", {})
        picked = summarize_all(picked, model=llm_cfg.get("model") or None,
                               pause=float(llm_cfg.get("pause_seconds", 4.0)),
                               max_calls=llm_cfg.get("max_calls_per_run", 50),
                               stop_after=top_n if gate_on else None)

    picked = redact_articles(picked, "요약")   # LLM이 본문의 토큰을 요약문에 되뱉는 경우
    picked, irrelevant = drop_irrelevant(picked) if gate_on else (picked, [])

    # 한도 등으로 요약을 못 받은 기사는 게시하지 않는다 — seen에도 안 넣으므로
    # 다음 실행에서 다시 후보로 탐지된다 (SPEC 1.6)
    ready = [a for a in picked if a.get("llm_done")]
    # 여유분(overpick)을 뽑았으므로 다시 top_n으로 줄인다. 앞에서 그냥 자르면
    # 예약석(source_quota) 비율이 깨지므로 같은 선별 규칙을 한 번 더 태운다.
    if gate_on:
        ready = pick(ready, top_n, sc.get("per_source", 5),
                     quota=cfg.get("source_quota", {}), per_feed_page=per_feed_page)
    # 닫힌 어휘 태깅 (SPEC 1B) — 규칙 기반이라 LLM 예산을 쓰지 않는다
    return tag_all(ready), irrelevant, dead_links


def write_outputs(published: list[dict], cfg: dict, now, out: str) -> None:
    """아카이브 → 검색 인덱스 → 페이지 → docs 사본 → API 카탈로그."""
    sc = cfg.get("scraper", {})
    if published:
        all_articles = archive.append(published, now)
    else:
        print("[한도] 이번 회차 게시 0건 — 기존 페이지 유지")
        all_articles = archive.load_all()

    archive.write_search_index(all_articles)
    display = archive.recent(all_articles, sc.get("keep_days", 30))
    render(display, out, collected=now, enabled=cfg.get("sources", {}),
           ads=cfg.get("ads"))
    sync_docs_data()
    # API 카탈로그 (add-public-apis-feeds) — 실패해도 회차를 죽이지 않는다
    apis_catalog.sync(os.path.join(ROOT, "docs", "data", "apis.json"),
                      health=cfg.get("apis", {}).get("health"),
                      cache_path=os.path.join(ROOT, "data", "api_health.json"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="sample.json으로 렌더만 수행")
    ap.add_argument("--no-ai", action="store_true", help="LLM 요약 건너뛰기")
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "index.html"))
    args = ap.parse_args()

    load_dotenv()
    cfg = load_config()

    if args.demo:
        with open(os.path.join(ROOT, "sample.json"), encoding="utf-8") as f:
            render(json.load(f), args.out, enabled=cfg.get("sources", {}),
                   ads=cfg.get("ads"))
        return 0

    now = datetime.now(KST)
    min_published = cfg.get("alert", {}).get("min_published", 0)
    archive.migrate_legacy()               # 단일 articles.json → 월별 샤드 (멱등)

    articles = collect_candidates(cfg)
    picked = select_articles(articles, cfg, now, now.strftime("%Y-%m-%d"))

    if not picked:
        print("새 기사가 없습니다. 기존 페이지를 유지합니다.")
        emit_actions_output(0, min_published)
        return 0

    published, irrelevant, dead_links = prepare_published(picked, cfg, args.no_ai)
    write_outputs(published, cfg, now, args.out)

    # 무관·죽은 링크 판정분도 기억한다 — 안 그러면 다음 회차에 다시 후보로
    # 올라와 같은 기사에 LLM 호출을 반복한다.
    seen_db.mark_seen(published + irrelevant + dead_links)
    emit_actions_output(len(published), min_published)
    return 0


if __name__ == "__main__":
    sys.exit(main())
