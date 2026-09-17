"""skills.sh 리더보드 스냅샷 → docs/data/skills.json

skills.sh 는 Vercel 이 여는 에이전트 스킬 디렉토리다. 첫 화면이 누적 설치 순위,
/trending 이 최근 8주 활동 순위다. 공개 API 는 없고(robots.txt 가 /api/ 를
막는다) 목록 페이지 자체는 허용돼 있어 그 HTML 을 읽는다.

API 카탈로그(apis_catalog)와 같은 자리다 — 기사 파이프라인과 무관한 부가
산출물이라 실패해도 회차를 죽이지 않고 기존 파일을 둔다.

지난 스냅샷과 견줘 순위 변화를 붙인다. 순위표만으로는 "뭐가 새로 올라왔나"를
알 수 없어서다.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from news.core import http

SITE = "https://www.skills.sh"
PAGES = {"trending": "/trending", "top": "/"}
MIN_ROWS = 50        # 이보다 적게 읽히면 화면이 바뀐 것이다 — 기존 파일을 지킨다
KEEP = 100           # 목록마다 앞에서부터 이만큼
DESC_PER_RUN = 60    # 한 회차에 새로 읽는 설명 수. 나머지는 다음 회차가 채운다
DESC_WORKERS = 6

_NUM = re.compile(r"^([\d.]+)\s*([KMB]?)$", re.I)


def _metric(text: str) -> int | None:
    m = _NUM.match(text.strip().replace(",", ""))
    if not m:
        return None
    n = float(m.group(1))
    return int(n * {"": 1, "K": 1e3, "M": 1e6, "B": 1e9}[m.group(2).upper()])


def parse_rows(html: str) -> list[dict]:
    """순위표 한 페이지를 행 목록으로.

    행은 <a href="/owner/repo/skill"> 안에 순위(span) · 이름(h3) · owner/repo(p) ·
    수치(마지막 글자) 순으로 들어 있다. 구조가 바뀌면 빈 목록이 나오고 sync 가
    MIN_ROWS 로 잡는다.
    """
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.select("a[href]"):
        h3 = a.select_one("h3")
        href = a.get("href") or ""
        if not h3 or href.count("/") < 3 or not href.startswith("/"):
            continue
        parts = href.strip("/").split("/")
        if len(parts) < 3:
            continue
        texts = [t.get_text(" ", strip=True) for t in a.find_all(["span", "h3", "p"])]
        texts = [t for t in texts if t]
        rank = next((int(t) for t in texts if t.isdigit()), None)
        metric = next((_metric(t) for t in reversed(texts) if _metric(t) is not None), None)
        if rank is None:
            continue
        out.append({
            "rank": rank, "name": h3.get_text(strip=True),
            "owner": parts[0], "repo": parts[1],
            "url": SITE + "/" + "/".join(parts[:3]),
            "metric": metric,
        })
    out.sort(key=lambda r: r["rank"])
    # 페이지가 일부 행을 안 내려준다(1, 5, 9…처럼 빈 자리가 생긴다). 화면에서는
    # 받은 순서대로 다시 매기고, 사이트 쪽 번호는 site_rank 로 남긴다.
    for i, r in enumerate(out, 1):
        r["site_rank"], r["rank"] = r["rank"], i
    return out[:KEEP]


def _key(r: dict) -> str:
    return f'{r["owner"]}/{r["repo"]}/{r["name"]}'


def with_delta(rows: list[dict], previous: list[dict] | None) -> list[dict]:
    """지난 스냅샷의 순위를 prev 로 붙인다. 없던 항목은 prev=None(새로 진입)."""
    prev = {_key(r): r["rank"] for r in (previous or [])}
    return [{**r, "prev": prev.get(_key(r))} for r in rows]


def parse_desc(html: str) -> str:
    """스킬 페이지의 meta description. 사이트가 SKILL.md 의 description 을 그대로
    넣어 준다(영문, 160자쯤에서 …로 잘림)."""
    soup = BeautifulSoup(html, "html.parser")
    m = soup.select_one('meta[name="description"]') or soup.select_one('meta[property="og:description"]')
    return (m.get("content") or "").strip() if m else ""


def fill_descs(rows: list[dict], previous: list[dict], fetch=None, limit: int = DESC_PER_RUN) -> int:
    """설명을 채운다. 지난 스냅샷에 있던 것은 그대로 쓰고, 없는 것만 페이지를
    읽는다 — 한 회차에 limit 개까지. 그래서 첫 회차 뒤로는 새 스킬 몇 개만
    읽는다. 못 읽은 것은 빈 채로 두고 다음 회차가 다시 시도한다."""
    from concurrent.futures import ThreadPoolExecutor
    fetch = fetch or fetch_page
    known = {_key(r): r.get("desc") for r in (previous or []) if r.get("desc")}
    todo = []
    for r in rows:
        r["desc"] = known.get(_key(r), "")
        if not r["desc"]:
            todo.append(r)
    todo = todo[:limit]

    def one(r):
        try:
            return parse_desc(fetch(r["url"][len(SITE):]))
        except Exception:
            return ""
    with ThreadPoolExecutor(DESC_WORKERS) as pool:
        for r, d in zip(todo, pool.map(one, todo)):
            r["desc"] = d
    return sum(1 for r in todo if r["desc"])


def fetch_page(path: str) -> str:
    resp = http.get_capped(SITE + path, timeout=20)
    resp.raise_for_status()
    return resp.text


def _previous(out_path: str) -> dict:
    try:
        with open(out_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def build(out_path: str, fetch=None) -> dict:
    fetch = fetch or fetch_page          # 실행 시점에 찾는다 — 테스트가 바꿔 끼울 수 있게
    previous = _previous(out_path)
    data = {"updated": datetime.now(timezone.utc).isoformat(), "site": SITE}
    lists = {}
    for key, path in PAGES.items():
        rows = parse_rows(fetch(path))
        if len(rows) < MIN_ROWS:
            raise RuntimeError(f"{path} 에서 {len(rows)}행만 읽혔다 — 화면이 바뀐 듯하다")
        lists[key] = with_delta(rows, previous.get(key))
    # 설명은 두 목록을 합쳐 한 번만 읽는다 — 같은 스킬이 양쪽에 있는 일이 많다
    prev_all = (previous.get("trending") or []) + (previous.get("top") or [])
    got = fill_descs(lists["trending"] + lists["top"], prev_all, fetch)
    seen: dict[str, str] = {}
    for r in lists["trending"] + lists["top"]:      # 한쪽에서 읽은 설명을 다른 쪽에도
        seen.setdefault(_key(r), r["desc"]) if r["desc"] else None
        r["desc"] = r["desc"] or seen.get(_key(r), "")
    data.update(lists)
    data["desc_fetched"] = got
    return data


def sync(out_path: str) -> bool:
    """실패하면 기존 파일을 그대로 두고 False. 회차를 죽이지 않는다."""
    try:
        data = build(out_path)
    except Exception as e:
        print(f"[skills] 순위 갱신 실패 — 기존 파일 유지: {e}")
        return False
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    new = sum(1 for r in data["trending"] if r["prev"] is None)
    missing = sum(1 for r in data["trending"] + data["top"] if not r.get("desc"))
    print(f"[skills] 순위 갱신: 상승 {len(data['trending'])}건(새 진입 {new}) · 누적 {len(data['top'])}건"
          f" · 설명 새로 읽음 {data.get('desc_fetched', 0)}건 · 아직 없음 {missing}건")
    return True
