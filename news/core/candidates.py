"""수집된 전 후보(선별 탈락분 포함)를 월별 판정 로그로 남긴다 (SPEC 1.4).

용도:
  ① 1B 단계에서 이 코퍼스를 분석해 태그 어휘 도출
  ② "선별된 기사 중 실제 보관/읽음 비율"로 판정 품질 측정
  ③ GitHub 스타의 전일 대비 증가량(Δ) 계산 재료 (SPEC 1.5)

LLM은 쓰지 않는다. GitHub 메타데이터(토픽·언어·라이선스·스타)는 REST API로 획득 —
비인증 시간당 60회, GITHUB_TOKEN이 있으면(Actions 기본 제공) 시간당 1,000회+.
월별 샤딩 규칙은 articles와 동일: 이번 달 파일만 수정한다.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime

from news.core import http

from news.core.common import ROOT  # noqa: E402  (경로 상수 재노출)
DIR = os.path.join(ROOT, "data", "candidates")

GITHUB_REPO_RE = re.compile(r"^https?://github\.com/([^/]+)/([^/?#]+?)(?:\.git)?(?:[/?#].*)?$")


def _shard_path(month: str, base_dir: str = DIR) -> str:
    return os.path.join(base_dir, f"{month}.json")


def _load(path: str) -> list:
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def github_meta(url: str, token: str | None = None) -> dict:
    """레포의 토픽·언어·라이선스·스타·포크. 실패하면 빈 dict (치명적이지 않음)."""
    m = GITHUB_REPO_RE.match(url)
    if not m:
        return {}
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "dev-news"}
    token = token or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        resp = http.get(f"https://api.github.com/repos/{m.group(1)}/{m.group(2)}",
                            headers=headers, timeout=10)
        if resp.status_code != 200:
            print(f"[candidates] GitHub API {resp.status_code}: {m.group(1)}/{m.group(2)}")
            return {}
        j = resp.json()
        return {
            "stars": j.get("stargazers_count"),
            "forks": j.get("forks_count"),
            "language": j.get("language"),
            "license": (j.get("license") or {}).get("spdx_id"),
            "topics": j.get("topics", []),
        }
    except Exception as e:
        print(f"[candidates] GitHub API 실패: {e}")
        return {}


def previous_stars(url: str, before_date: str, base_dir: str = DIR) -> int | None:
    """이전 날짜 스냅샷의 절대 스타 수. Δ = 오늘 스타 - 이 값. 없으면 None(첫 등장)."""
    months_avail = sorted((fn[:-5] for fn in os.listdir(base_dir) if fn.endswith(".json")),
                          reverse=True) if os.path.isdir(base_dir) else []
    for m in months_avail[:2]:                     # 이번 달 + 지난 달이면 충분
        for row in _load(_shard_path(m, base_dir)):
            if row.get("url") == url and row.get("date", "") < before_date:
                stars = (row.get("native") or {}).get("stars")
                if stars is not None:
                    return stars
    return None


def _native(article: dict, gh_meta: dict) -> dict:
    """소스가 원래 주는 메타데이터를 원본 그대로 담는다."""
    native = {"upvotes": article.get("upvotes", 0), "comments": article.get("comments", 0)}
    for key in ("feed", "subreddit", "tags"):
        if article.get(key):
            native[key] = article[key]
    if article.get("source") == "github":
        native["stars_today"] = article.get("upvotes", 0)
        native.update(gh_meta)
    return native


def log(cands: list[dict], selected_urls: set[str], batch: datetime,
        gh_meta_map: dict[str, dict] | None = None, base_dir: str = DIR) -> None:
    """오늘 후보 전체를 (url, date) 단위로 기록. 같은 날 재실행 시 selected만 갱신."""
    gh_meta_map = gh_meta_map or {}
    date = batch.strftime("%Y-%m-%d")
    month = date[:7]
    shard = _load(_shard_path(month, base_dir))
    by_key = {(r.get("url"), r.get("date")): r for r in shard}

    added = 0
    for a in cands:
        key = (a.get("url"), date)
        row = {
            "url": a.get("url", ""),
            "title": a.get("title", ""),
            "description": (a.get("description") or "")[:500],
            "source": a.get("source", ""),
            "native": _native(a, gh_meta_map.get(a.get("url", ""), {})),
            "selected": a.get("url") in selected_urls,
            "date": date,
        }
        if key in by_key:
            by_key[key]["selected"] = by_key[key]["selected"] or row["selected"]
        else:
            by_key[key] = row
            added += 1

    rows = sorted(by_key.values(), key=lambda r: (r.get("date", ""), r.get("source", "")), reverse=True)
    os.makedirs(base_dir, exist_ok=True)
    with open(_shard_path(month, base_dir), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    print(f"[candidates] 오늘 {added}건 기록 (선별 {len(selected_urls)}건 표시) · 이번 달 누적 {len(rows)}건")
