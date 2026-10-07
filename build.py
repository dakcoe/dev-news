#!/usr/bin/env python3
"""개발·AI 뉴스 페이지 빌더.

  python build.py            # 수집 → 요약 → docs/index.html 생성
  python build.py --demo     # 네트워크·LLM 없이 sample.json으로 렌더만 (레이아웃 확인용)
  python build.py --no-ai    # 수집은 하되 LLM 요약은 건너뜀 (원문 설명 그대로 사용)

환경변수
  LLM_PROVIDER   groq(기본) — Groq 전용, 새 공급자 추가 금지 (SPEC 불변 제약)
  GROQ_API_KEY   Groq API 키
  LLM_MODEL      모델을 직접 지정하고 싶을 때만
  GITHUB_TOKEN   있으면 GitHub API 한도가 시간당 60→1,000회+ (publish.sh 가 gh 토큰을 넣는다)

깔때기 (SPEC 1.2): 넓은 수집 → 차단어·기간 컷 → 중복 제거 + candidates 로그
→ 보조 점수 top_n 선별 → 최종 선별분만 본문·썸네일·요약 → 죽은 링크·무관 선언 컷.

SPEC 1.1 은 "파이프라인 수준의 차단 필터를 두지 않는다" 고 적었고 1.4 는
candidates 를 "전체 후보" 라고 부르지만, 지금은 둘 다 그대로가 아니다.
candidates 로그 앞에 keyword_filter(block_keywords)·recent_only 가 있어
후보의 20% 안팎이 기록 전에 빠진다. 1B 어휘 도출은 그 점을 알고 시작해야
한다 — "데이터는 전부 보존되므로 소급 적용이 가능하다" 가 빠진 몫에는
성립하지 않는다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime

import yaml

from news import apis_catalog, skills_catalog
from news.core import archive, candidates, source_health
from news.core import seen as seen_db
from news.core.dedup import merge_duplicates
from news.core.filters import (
    drop_dead_links,
    drop_old_giants,
    drop_irrelevant,
    drop_self_declared_irrelevant,
    keyword_filter,
    page_eligible,
    recent_only,
)
from news.core.select import adjust_scores, pick
from news.core.enrich import enrich
from news.core.redact import redact_articles
from news.core.scorer import score_and_categorize
from news.core.tags import tag_all
from news.render import render, write_seo_files
from news.scrapers import (anthropic, devto, geeknews, github, hackernews, lobsters,
                           reddit, rss, trendshift)

ROOT = os.path.dirname(os.path.abspath(__file__))
from news.core.common import KST  # noqa: E402  (상수 재노출)
# TRUSTED 는 news.core.filters 에만 둔다. 여기 사본이 있었는데 아무도 읽지
# 않는 사이 두 항목(hackernews·lobsters)이 저쪽에만 추가돼 값이 갈렸다.


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


def run_scrapers(cfg: dict, counts: dict[str, int] | None = None,
                 skip_days: dict[str, list[int]] | None = None) -> list[dict]:
    """출처별 수집. counts를 주면 출처 이름 → 건수를 채운다 (예외는 0건).

    skip_days를 주면 피드가 <skipDays>로 밝힌 휴재 요일을 함께 채운다.
    """
    s = cfg.get("scraper", {})
    src = cfg.get("sources", {})
    tasks = {}
    if src.get("hackernews", True):
        tasks["hackernews"] = lambda: hackernews.fetch(limit=s.get("hn_limit", 60))
    if src.get("github", True):
        tasks["github"] = lambda: github.fetch()
    if src.get("trendshift", True):
        tasks["trendshift"] = lambda: trendshift.fetch()   # source=github, feed=Trendshift
    # per_source 는 선별 상한(한 출처 최대 5건)이다. 수집 개수로 읽으면 후보가 5건뿐이라
    # 선별이 고를 게 없다 — lobsters·geeknews 가 그렇게 5건씩만 받고 있었다.
    fetch_n = s.get("per_source_fetch", 30)
    if src.get("lobsters", True):
        tasks["lobsters"] = lambda: lobsters.fetch(limit=fetch_n)
    if src.get("devto", True):
        tasks["devto"] = lambda: devto.fetch(tags=s.get("devto_tags"), counts=counts)
    if src.get("reddit", False):
        tasks["reddit"] = lambda: reddit.fetch(subreddits=s.get("subreddits"))
    if src.get("geeknews", True):
        tasks["geeknews"] = lambda: geeknews.fetch(limit=fetch_n, counts=counts)
    if src.get("rss", True):
        # counts를 넘겨 피드별 건수를 남긴다. 합계만 기록하면 피드 하나가 죽어도
        # rss 총계가 0이 아니라 출처 침묵 경고가 영영 안 뛴다.
        tasks["rss"] = lambda: rss.fetch(cfg.get("feeds"), per_feed=s.get("per_feed", 8),
                                         counts=counts, skip_days=skip_days)
    if src.get("anthropic", True):
        # rss 와 같은 이유로 하위 수집원(뉴스·엔지니어링·Claude 블로그·개발자 블로그)별로 센다
        tasks["anthropic"] = lambda: anthropic.fetch(limit=s.get("per_feed", 8), counts=counts)

    articles: list[dict] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(fn): name for name, fn in tasks.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                got = future.result()
                print(f"[{name}] {len(got)}개 수집")
                articles.extend(got)
                if counts is not None:
                    counts[name] = len(got)
            except Exception as e:
                print(f"[{name}] 실패: {e}")
                if counts is not None:
                    counts[name] = 0
    return articles


def _is_yesterday(snapshot_date: str, today: str) -> bool:
    try:
        d = date.fromisoformat(today) - date.fromisoformat(snapshot_date)
    except ValueError:
        return False
    return d.days == 1


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
        # 어제 스냅샷일 때만 뺀다. 그보다 오래된 것을 쓰면 며칠치 증가분이
        # 하루치 Δ 로 나가고, 옆줄의 하루치 숫자와 비교가 안 된다.
        # 그럴 때는 trending 이 직접 주는 stars today 가 더 정확하다.
        if meta.get("stars") is not None and prev is not None and _is_yesterday(prev[1], today):
            delta = max(meta["stars"] - prev[0], 0)
        else:
            delta = a.get("upvotes", 0)        # 첫 등장이거나 간격이 벌어짐
        a["upvotes"] = delta
        a["delta_stars"] = delta
    if gh_items:
        print(f"[Δ] GitHub {len(gh_items)}건 스타 증가량 적용")
    return meta_map


def emit_actions_output(published: int, min_published: int,
                        silent: list[str] | None = None,
                        warnings: list[str] | None = None) -> bool:
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
            f.write(f"silent={','.join(silent or [])}\n")
            # 한 줄에 담아야 셸의 val() 이 읽는다
            f.write(f"warn={' / '.join(warnings or [])}\n")
    if degraded:
        print(f"[알림] 게시 {published}건 — 임계 {min_published}건 미만이라 열화로 보고합니다")
    return degraded


def _gate_settings(cfg: dict) -> tuple[int, bool, int, int | None]:
    """설정에서 파생되는 선별 값들. 여러 단계가 같은 값을 봐야 해서 한곳에 둔다."""
    sc = cfg.get("scraper", {})
    top_n = sc.get("top_n", 20)
    gate_on = bool(sc.get("relevance_gate", False))
    # 게이트가 꺼져 있으면 여유분도 0 — 동작이 도입 전과 완전히 같아진다
    overpick = sc.get("overpick", 5) if gate_on else 0
    return top_n, gate_on, overpick, sc.get("per_feed_page")


def check_source_silence(counts: dict[str, int], cfg: dict, when: str,
                         skip_days: dict[str, list[int]] | None = None,
                         recent: dict[str, int] | None = None) -> list[str]:
    """출처별 건수를 기록하고 연속 0건인 출처를 돌려준다 (add-source-silence-alert).

    휴재 요일을 밝힌 출처는 그 요일 회차를 세지 않는다 — arXiv는 주말에 항목이
    없는 껍데기를 주므로, 그걸 모르면 매주 토·일에 죽은 출처로 잡힌다.

    recent(기간 필터 뒤 건수)를 주면 옛 글만 계속 돌려주는 출처도 함께 돌려준다.
    알림 문구가 '연속 0건인 출처'라 이름 뒤에 '(기간 내 0건)'을 붙여 구분한다.
    """
    alert = cfg.get("alert", {})
    streak = alert.get("silent_streak", source_health.DEFAULT_STREAK)
    history = source_health.record(counts, when, skip_days=skip_days, recent=recent)
    quiet = source_health.silent(history, streak)
    if quiet:
        print(f"[알림] {streak}회차 연속 0건 출처: {', '.join(quiet)}")
    stale_streak = alert.get("stale_streak", source_health.DEFAULT_STALE_STREAK)
    old_only = [n for n in source_health.stale(history, stale_streak) if n not in quiet]
    if old_only:
        print(f"[알림] {stale_streak}회차 연속 기간 내 0건 출처(옛 글만 옴): {', '.join(old_only)}")
    return quiet + [f"{n}(기간 내 0건)" for n in old_only]


# 수집·선별·요약·출력의 실패 지점을 따로 확인하려고 main의 단계를 나눴다 (split-main).
def collect_candidates(cfg: dict, when: str = "") -> tuple[list[dict], list[str]]:
    """수집 → 필터 → 중복 제거. 깔때기의 넓은 쪽 (SPEC 1.2).

    출처별 건수는 여기서 기록하고, 침묵 출처 목록을 두 번째 값으로 돌려준다.
    """
    sc = cfg.get("scraper", {})
    counts: dict[str, int] = {}
    skip_days: dict[str, list[int]] = {}
    raw = run_scrapers(cfg, counts, skip_days)
    articles = keyword_filter(raw, cfg.get("keywords", []), cfg.get("block_keywords"))
    articles = recent_only(articles, sc.get("window_hours", 48), cfg.get("long_window", {}))
    # 수집 건수만 기록하면 옛 글만 계속 돌려주는 피드가 매 회차 8건으로 보인다.
    # 기간 필터 뒤 건수도 같이 남긴다. 중복 제거 전에 세야 출처별 몫이 그대로다.
    quiet = check_source_silence(counts, cfg, when, skip_days,
                                 recent=source_health.recent_counts(articles, counts))
    articles = merge_duplicates(articles)
    # 남의 글에 박힌 토큰이 candidates 로그·아카이브에 실려 push되면 GitHub Push
    # Protection이 push를 거부해 회차 전체가 죽는다 (run 31510062957)
    articles = redact_articles(articles, "수집")
    print(f"[깔때기] 후보 {len(raw)}건 → 필터·중복 제거 후 {len(articles)}건")
    return articles, quiet


def select_articles(articles: list[dict], cfg: dict, now, today: str) -> list[dict]:
    """점수 → 미소개분 → 예약석·상한 적용. 판정 로그도 여기서 남긴다 (SPEC 1.4)."""
    sc = cfg.get("scraper", {})
    top_n, _, overpick, per_feed_page = _gate_settings(cfg)

    gh_meta_map = apply_star_delta(articles, today)
    old = sc.get("old_repo") or {}
    articles = drop_old_giants(articles, gh_meta_map, old.get("min_age_days", 365),
                               old.get("min_stars", 30000))
    articles = score_and_categorize(articles, top_n=len(articles))
    articles = adjust_scores(articles, cfg)

    fresh = seen_db.filter_unseen(page_eligible(articles),
                                  resurface_days=(cfg.get("seen") or {}).get("resurface_days"))
    picked = pick(fresh, top_n + overpick, sc.get("per_source", 5),
                  quota=cfg.get("source_quota", {}), per_feed_page=per_feed_page,
                  quota_backfill=cfg.get("quota_backfill", {}),
                  quota_backfill_max=cfg.get("quota_backfill_max", {}))
    print(f"[깔때기] 미소개 {len(fresh)}건 → 최종 선별 {len(picked)}건 "
          f"(목표 {top_n} + 여유 {overpick})")

    candidates.log(articles, {a["url"] for a in picked}, now, gh_meta_map)
    return picked


def _filter_summarized(arts: list[dict], gate_on: bool, recent: list[dict],
                       same_story: bool = True) -> tuple[list[dict], list[dict]]:
    """요약을 받은 뒤의 제외 단계를 한꺼번에 태운다. (남길 것, 뺀 것)을 돌려준다.

    요약을 못 받은 기사(llm_done=False)는 남길 것에도 뺀 것에도 넣지 않는다 —
    seen 에 안 들어가야 다음 회차에 다시 후보가 된다 (SPEC 1.6).
    """
    arts = redact_articles(arts, "요약")   # LLM이 본문의 토큰을 요약문에 되뱉는 경우
    arts, irrelevant = drop_irrelevant(arts) if gate_on else (arts, [])
    # 요약이 스스로 '개발자 업무와 무관'이라고 말한 기사. 추가 호출이 없어
    # 분류 게이트와 별개로 항상 켠다.
    arts, self_irrelevant = drop_self_declared_irrelevant(arts)
    ready = [a for a in arts if a.get("llm_done")]
    # 주소·제목으로 못 잡은 같은 사건을 요약까지 본 뒤 거른다. 빠진 것은 seen 에
    # 넣는다 — 안 넣으면 회차마다 다시 뽑혀 요약을 또 받고, 원본이 48시간 창을
    # 벗어나면 그대로 실린다.
    same: list[dict] = []
    if same_story:
        from news.core.similar import drop_same_story
        ready, same = drop_same_story(ready, recent)
    return ready, irrelevant + self_irrelevant + same


def prepare_published(picked: list[dict], cfg: dict,
                      no_ai: bool) -> tuple[list[dict], list[dict], list[dict]]:
    """본문·요약·태깅. (게재분, 무관 제외분, 죽은 링크 제외분)을 돌려준다.

    게재 기준이 켜져 있으면 후보를 top_n + overpick 만큼 받아 온다. 요약은 그중
    예약석 규칙으로 고른 top_n 건(본선)부터 받고, 제외 단계를 다 거친 뒤 모자란
    만큼만 나머지(예비)에서 더 요약한다.

    전에는 점수순으로 요약하다 게재 가능분이 top_n 에 닿으면 멈추고, 같은 사건·
    무관 선언 제외는 그 뒤에 했다. 그러면 뺀 자리를 메울 요약분이 없어서 9/17~10/7
    62회차가 한 번도 20건을 채우지 못했다(평균 17.1건). 점수가 낮은 github 는
    요약 순서 맨 뒤라 먼저 잘려 예약석 5칸이 59회차에서 비었다.
    """
    sc = cfg.get("scraper", {})
    top_n, gate_on, _, per_feed_page = _gate_settings(cfg)
    pick_rules = dict(quota=cfg.get("source_quota", {}), per_feed_page=per_feed_page,
                      quota_backfill=cfg.get("quota_backfill", {}),
                      quota_backfill_max=cfg.get("quota_backfill_max", {}))

    # 본문은 여기서 처음 들어온다. 요약 요청 전에 지워야 남의 토큰이 LLM
    # 공급자에게 전송되는 것까지 막힌다.
    from news.core.discussion import fill_from_discussion
    # 본문을 못 가져온 기사는 그 글의 댓글로 메운다. 마스킹 앞에 두어 댓글에
    # 섞인 토큰도 같이 걸러진다.
    picked = redact_articles(fill_from_discussion(enrich(picked)), "본문")
    # 죽은 링크는 요약 전에 뺀다 — LLM 호출을 쓰지 않게 된다
    picked, dead_links = drop_dead_links(picked)

    from news.core.similar import recent_published
    recent = recent_published(archive.load_all(), datetime.now(KST))

    if no_ai:
        for a in picked:
            a.setdefault("summary", a.get("description", ""))
            a["llm_done"] = True
        # 같은 사건 판정은 Groq 를 부르고 1GB 모델을 올린다. 요약 없이 돌려 보는
        # 실행에서 그럴 이유가 없다.
        ready, removed = _filter_summarized(picked, gate_on, recent, same_story=False)
    else:
        from news import summarizer
        llm_cfg = cfg.get("llm", {})
        budget = llm_cfg.get("max_calls_per_run", 50)

        def summarize(arts, stop_after=None):
            # 본선과 예비가 호출 예산 하나를 나눠 쓴다
            nonlocal budget
            stats: dict = {}
            out = summarizer.summarize_all(
                arts, model=llm_cfg.get("model") or None,
                pause=float(llm_cfg.get("pause_seconds", 4.0)),
                max_calls=budget, stop_after=stop_after,
                why_model=llm_cfg.get("why_model") or None,
                fallback_models=llm_cfg.get("fallback_models"),
                why_fallback_models=llm_cfg.get("why_fallback_models"), stats=stats)
            budget -= stats.get("calls", 0)
            return out

        if gate_on:
            main = pick(picked, top_n, sc.get("per_source", 5), **pick_rules)
            main_urls = {a["url"] for a in main}
            reserve = [a for a in picked if a["url"] not in main_urls]
        else:
            main, reserve = picked, []
        ready, removed = _filter_summarized(summarize(main), gate_on, recent)
        # 본선에서 빠진 만큼만 채운다. top_n 과의 차이로 잡으면 pick 이 일부러 비워 둔
        # 예약석(github 후보 부족)까지 메우려다, 요약만 받고 마지막 pick 에서 잘리는
        # 기사가 생긴다 — 9/17~10/7 62회차 중 59회차가 그런 회차였다.
        short = len(main) - len(ready)
        if gate_on and short > 0 and reserve and budget > 0:
            print(f"[깔때기] 게재 가능 {len(ready)}건 — 예비 {len(reserve)}건에서 {short}건 보충")
            more = summarize(reserve, stop_after=short)
            # 예비분끼리만이 아니라 이미 남긴 본선과도 같은 사건인지 본다
            more_ready, more_removed = _filter_summarized(more, gate_on, recent + ready)
            ready, removed = ready + more_ready, removed + more_removed

    # 여유분(overpick)을 뽑았으므로 다시 top_n으로 줄인다. 앞에서 그냥 자르면
    # 예약석(source_quota) 비율이 깨지므로 같은 선별 규칙을 한 번 더 태운다.
    if gate_on:
        ready = pick(ready, top_n, sc.get("per_source", 5), **pick_rules)
    # 닫힌 어휘 태깅 (SPEC 1B) — 규칙 기반이라 LLM 예산을 쓰지 않는다
    return tag_all(ready), removed, dead_links


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
    render(display, out, collected=now, enabled=cfg.get("sources", {}), about=cfg.get("about"),
           ads=cfg.get("ads"))
    write_seo_files(os.path.dirname(out), now)
    # API 카탈로그 (add-public-apis-feeds) — 실패해도 회차를 죽이지 않는다
    apis_catalog.sync(os.path.join(ROOT, "docs", "data", "apis.json"),
                      health=cfg.get("apis", {}).get("health"),
                      cache_path=os.path.join(ROOT, "data", "api_health.json"))
    # 에이전트 스킬 순위 (skills.sh) — 같은 이유로 실패해도 회차를 죽이지 않는다
    skills_catalog.sync(os.path.join(ROOT, "docs", "data", "skills.json"))


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
            render(json.load(f), args.out, enabled=cfg.get("sources", {}), about=cfg.get("about"),
                   ads=cfg.get("ads"))
        return 0

    now = datetime.now(KST)
    min_published = cfg.get("alert", {}).get("min_published", 0)
    archive.migrate_legacy()               # 단일 articles.json → 월별 샤드 (멱등)

    articles, silent = collect_candidates(cfg, now.isoformat(timespec="minutes"))
    picked = select_articles(articles, cfg, now, now.strftime("%Y-%m-%d"))

    if not picked:
        print("새 기사가 없습니다. 기존 페이지를 유지합니다.")
        emit_actions_output(0, min_published, silent)
        return 0

    published, irrelevant, dead_links = prepare_published(picked, cfg, args.no_ai)
    write_outputs(published, cfg, now, args.out)

    # 무관·죽은 링크 판정분도 기억한다 — 안 그러면 다음 회차에 다시 후보로
    # 올라와 같은 기사에 LLM 호출을 반복한다.
    seen_db.mark_seen(published + irrelevant + dead_links)
    from news.core import similar
    emit_actions_output(len(published), min_published, silent, list(similar.WARNINGS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
