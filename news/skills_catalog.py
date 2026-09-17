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
KO_PER_RUN = 60      # 한 회차에 번역하는 설명 수 (10개씩 묶어 부르므로 호출 6회)
KO_BATCH = 10

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


KO_PROMPT = """아래 영문 설명들을 각각 자연스러운 한국어 한두 문장으로 옮겨라.
제품명·도구명·명령어·저장소명 같은 고유명사와 코드는 영문 그대로 둔다. 원문에 없는 내용을 덧붙이지 마라.
출력은 번호와 번역문만, 한 줄에 하나씩. 다른 말은 붙이지 마라.

{items}
"""


def _parse_numbered(text: str, n: int) -> list[str] | None:
    """"1. …" 꼴 n 줄을 순서대로. 개수가 안 맞으면 None — 다음 회차에 다시 한다."""
    import re as _re
    found = {}
    for line in text.splitlines():
        m = _re.match(r"\s*(\d+)[.)]\s*(.+)", line)
        if m:
            found[int(m.group(1))] = m.group(2).strip()
    out = [found.get(i + 1, "") for i in range(n)]
    return out if all(out) else None


def translate_descs(rows: list[dict], previous: list[dict], call=None,
                    limit: int = KO_PER_RUN, batch: int = KO_BATCH) -> int:
    """영문 설명을 한국어로. 지난 스냅샷의 번역은 이어받고 없는 것만 부른다.

    호출은 요약기와 같은 경로(summarizer._call)다. 열 개씩 묶어 한 번에 보내
    회차당 호출을 몇 번으로 줄인다. 번역에 한자·가나가 섞이면 버린다 — 요약과
    같은 기준이다. 키가 없으면(로컬 실행) 아무것도 안 한다."""
    from news import summarizer as S
    known = {_key(r): r.get("desc_ko") for r in (previous or []) if r.get("desc_ko")}
    todo = []
    for r in rows:
        r["desc_ko"] = known.get(_key(r), "")
        if r.get("desc") and not r["desc_ko"]:
            todo.append(r)
    todo = todo[:limit]
    if not todo:
        return 0
    api_key = os.environ.get("GROQ_API_KEY") or ""
    if call is None:
        if not api_key:
            return 0
        model = S.DEFAULT_MODELS.get("groq")
        call = lambda prompt: S._call(prompt, "groq", model, api_key)
    done = 0
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        items = "\n".join(f"{j + 1}. {r['desc']}" for j, r in enumerate(chunk))
        try:
            got = _parse_numbered(call(KO_PROMPT.format(items=items)), len(chunk))
        except Exception as e:
            print(f"[skills] 번역 호출 실패 — 다음 회차에 다시: {e}")
            break
        if not got:
            continue
        for r, ko in zip(chunk, got):
            if S.FOREIGN_RE.search(ko):
                continue
            r["desc_ko"] = ko
            done += 1
    return done


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


def build(out_path: str, fetch=None, translate=None) -> dict:
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
    # 번역도 같은 식으로 — 두 목록을 합쳐 한 번, 한쪽 결과를 다른 쪽에도
    uniq: dict[str, dict] = {}
    for r in lists["trending"] + lists["top"]:
        uniq.setdefault(_key(r), r)
    ko = translate_descs(list(uniq.values()), prev_all, translate)
    for r in lists["trending"] + lists["top"]:
        r["desc_ko"] = uniq[_key(r)].get("desc_ko", "")
    data.update(lists)
    data["desc_fetched"] = got
    data["ko_translated"] = ko
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
    no_ko = sum(1 for r in data["trending"] + data["top"] if r.get("desc") and not r.get("desc_ko"))
    print(f"[skills] 순위 갱신: 상승 {len(data['trending'])}건(새 진입 {new}) · 누적 {len(data['top'])}건"
          f" · 설명 새로 읽음 {data.get('desc_fetched', 0)}건 · 아직 없음 {missing}건"
          f" · 번역 {data.get('ko_translated', 0)}건 · 미번역 {no_ko}건")
    return True
