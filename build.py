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
import re
import shutil
import sys
from collections import defaultdict
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

import yaml

from news import apis_catalog
from news.core import archive, candidates
from news.core import seen as seen_db
from news.core.dedup import merge_duplicates
from news.core.enrich import enrich
from news.core.redact import redact_articles
from news.core.scorer import score_and_categorize
from news.core.tags import tag_all
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


@lru_cache(maxsize=8)
def _keyword_re(keywords: tuple[str, ...]) -> re.Pattern[str]:
    """키워드 목록을 단어경계 정규식 하나로 컴파일한다.

    부분문자열 매칭(`"ai" in "said"`)이면 필터가 통째로 무력해진다 — 실측으로
    미신뢰 출처 167건 중 166건이 통과했다. 그래서 앞뒤를 영숫자로 막는다.

    형태소는 허용하되 길이로 차등한다. 4글자 이상은 복수·시제 어미까지 받고
    (`containers`·`released`), 3글자 이하는 복수형만 받는다 — 짧은 키워드에 시제
    어미를 허용하면 `going`(go+ing)·`aid`(ai+d)가 다시 새기 때문이다.

    한글은 영숫자가 아니므로 한국어 제목은 이 경계 조건에 영향받지 않는다.
    """
    short = sorted((k for k in keywords if len(k) <= 3), key=len, reverse=True)
    long_ = sorted((k for k in keywords if len(k) > 3), key=len, reverse=True)
    parts = []
    if long_:
        parts.append("(?:" + "|".join(re.escape(k) for k in long_) + ")(?:s|es|ed|ing|d)?")
    if short:
        parts.append("(?:" + "|".join(re.escape(k) for k in short) + ")s?")
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(parts) + r")(?![a-z0-9])")


@lru_cache(maxsize=8)
def _block_re(ko: tuple[str, ...], en: tuple[str, ...]) -> re.Pattern[str] | None:
    """비개발 주제 차단 정규식.

    영어는 단어경계로 막는다 — 경계가 없으면 `war`가 `software`·`hardware`
    안에서 걸린다(실측 오탐). 한국어는 영숫자 경계가 통하지 않아 부분문자열로
    매칭되므로, `배우`(→배우다)처럼 다른 말에 파묻히는 모호어는 목록에 넣지
    않는 것으로 대응한다.
    """
    parts = []
    if ko:
        parts.append("(?:" + "|".join(re.escape(k) for k in ko) + ")")
    if en:
        parts.append(r"(?<![a-z0-9])(?:" + "|".join(re.escape(k) for k in en)
                     + r")(?![a-z0-9])")
    return re.compile("|".join(parts)) if parts else None


def keyword_filter(articles: list[dict], keywords: list[str],
                   block_keywords: dict | None = None) -> list[dict]:
    """개발 키워드로 거르고(화이트리스트), 비개발 주제를 뺀다(블랙리스트).

    화이트리스트는 TRUSTED 출처를 면제한다 — 키워드 140개에 한국어가 없어서
    긱뉴스 한국어 제목이 통과할 수 없기 때문이다. 그런데 그 면제 때문에
    비개발 기사가 그대로 실렸다(2026-08-30 배치 20건 중 4건).

    그래서 차단은 TRUSTED에도 적용한다. 면제는 "통과시킬 이유"에만 해당하지
    "빼지 않을 이유"는 아니다. 다만 차단어가 있어도 개발 키워드가 하나라도
    같이 있으면 남긴다 — `캘리포니아주 의회, 연령 확인법에서 Linux 면제`처럼
    정치 어휘를 쓰는 개발 기사를 잃지 않기 위해서다.
    """
    block_keywords = block_keywords or {}
    block = _block_re(
        tuple(k for k in (block_keywords.get("ko") or [])),
        tuple(k.lower() for k in (block_keywords.get("en") or [])),
    )
    pattern = _keyword_re(tuple(k.lower() for k in keywords)) if keywords else None

    kept, dropped, blocked = [], 0, 0
    for a in articles:
        text = (a.get("title", "") + " " + a.get("description", "")).lower()
        has_dev = bool(pattern.search(text)) if pattern else False

        if block is not None and block.search(text) and not has_dev:
            blocked += 1
            continue

        if pattern is None or a["source"] in TRUSTED or has_dev:
            kept.append(a)
        else:
            dropped += 1

    if dropped:
        print(f"[필터] 키워드 불일치 {dropped}건 제외")
    if blocked:
        print(f"[필터] 비개발 주제 {blocked}건 제외")
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


def dedupe(articles: list[dict]) -> list[dict]:
    """배치 내 중복 제거 (여러 소스가 같은 글을 물어오는 경우).

    URL 완전일치만 보던 것을 news.core.dedup으로 옮겼다 — 정규화 URL 1단,
    제목 유사도 2단. 합쳐진 항목은 cross_source_count를 들고 나가 scorer의
    가산에 쓰인다.
    """
    return merge_duplicates(articles)


def page_eligible(articles: list[dict]) -> list[dict]:
    """페이지 게재 자격이 있는 것만 남긴다 (SPEC 1.1 — 기록과 게재는 별개).

    코퍼스 전용 피드(config feeds의 page: false)는 candidates 로그에는 남되
    페이지 선별 대상에서는 빠진다. 플래그가 없는 아이템은 기존대로 게재 대상.
    """
    kept = [a for a in articles if a.get("page", True)]
    excluded = len(articles) - len(kept)
    if excluded:
        print(f"[선별] 코퍼스 전용 {excluded}건 페이지 제외")
    return kept


def adjust_scores(articles: list[dict], cfg: dict) -> list[dict]:
    """출처별 기본점수·가중치 보정 (deprecated — 동점 처리용으로만 남김, SPEC 1.5).

    UI에서 점수 표시는 제거됐다. 이 보정은 top_n 선별의 정렬 기준으로만 쓰인다.
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="sample.json으로 렌더만 수행")
    ap.add_argument("--no-ai", action="store_true", help="LLM 요약 건너뛰기")
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "index.html"))
    args = ap.parse_args()

    load_dotenv()

    if args.demo:
        with open(os.path.join(ROOT, "sample.json"), encoding="utf-8") as f:
            cfg = load_config()
            render(json.load(f), args.out, enabled=cfg.get("sources", {}),
                   ads=cfg.get("ads"))
        return 0

    cfg = load_config()
    sc = cfg.get("scraper", {})
    now = datetime.now(KST)
    today = now.strftime("%Y-%m-%d")

    archive.migrate_legacy()               # 단일 articles.json → 월별 샤드 (멱등)

    raw = run_scrapers(cfg)
    articles = keyword_filter(raw, cfg.get("keywords", []), cfg.get("block_keywords"))
    articles = recent_only(articles, sc.get("window_hours", 48), cfg.get("long_window", {}))
    articles = dedupe(articles)
    # 남의 글에 박힌 토큰이 candidates 로그·아카이브에 실려 push되면 GitHub Push
    # Protection이 push를 거부해 회차 전체가 죽는다 (run 31510062957)
    articles = redact_articles(articles, "수집")
    print(f"[깔때기] 후보 {len(raw)}건 → 필터·중복 제거 후 {len(articles)}건")

    gh_meta_map = apply_star_delta(articles, today)

    articles = score_and_categorize(articles, top_n=len(articles))
    articles = adjust_scores(articles, cfg)
    fresh = seen_db.filter_unseen(page_eligible(articles))
    picked = pick(fresh, sc.get("top_n", 20), sc.get("per_source", 5),
                  quota=cfg.get("source_quota", {}))
    print(f"[깔때기] 미소개 {len(fresh)}건 → 최종 선별 {len(picked)}건")

    # 판정 로그: 선별 탈락분 포함 전 후보를 기록 (SPEC 1.4)
    candidates.log(articles, {a["url"] for a in picked}, now, gh_meta_map)

    min_published = cfg.get("alert", {}).get("min_published", 0)

    if not picked:
        print("새 기사가 없습니다. 기존 페이지를 유지합니다.")
        emit_actions_output(0, min_published)
        return 0

    # 본문은 여기서 처음 들어온다. 요약 요청 전에 지워야 남의 토큰이 LLM 공급자에게
    # 전송되는 것까지 막힌다.
    picked = redact_articles(enrich(picked), "본문")

    if args.no_ai:
        for a in picked:
            a.setdefault("summary", a.get("description", ""))
            a["llm_done"] = True
    else:
        from news.summarizer import summarize_all
        llm_cfg = cfg.get("llm", {})
        picked = summarize_all(picked, model=llm_cfg.get("model") or None,
                               pause=float(llm_cfg.get("pause_seconds", 4.0)),
                               max_calls=llm_cfg.get("max_calls_per_run", 50))

    picked = redact_articles(picked, "요약")   # LLM이 본문의 토큰을 요약문에 되뱉는 경우

    # 한도 등으로 요약을 못 받은 기사는 게시하지 않는다 — seen에도 안 넣으므로
    # 다음 실행에서 다시 후보로 탐지된다 (SPEC 1.6)
    # 닫힌 어휘 태깅 (SPEC 1B) — 규칙 기반이라 LLM 예산을 쓰지 않는다
    published = tag_all([a for a in picked if a.get("llm_done")])

    if published:
        all_articles = archive.append(published, now)
    else:
        print("[한도] 이번 회차 게시 0건 — 기존 페이지 유지")
        all_articles = archive.load_all()

    archive.write_search_index(all_articles)
    display = archive.recent(all_articles, sc.get("keep_days", 30))
    render(display, args.out, collected=now, enabled=cfg.get("sources", {}),
           ads=cfg.get("ads"))
    sync_docs_data()
    # API 카탈로그 (add-public-apis-feeds) — 실패해도 회차를 죽이지 않는다
    apis_catalog.sync(os.path.join(ROOT, "docs", "data", "apis.json"),
                      health=cfg.get("apis", {}).get("health"),
                      cache_path=os.path.join(ROOT, "data", "api_health.json"))
    seen_db.mark_seen(published)
    emit_actions_output(len(published), min_published)
    return 0


if __name__ == "__main__":
    sys.exit(main())
