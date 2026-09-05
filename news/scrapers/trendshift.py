"""Trendshift 일간 순위 (add-trendshift-source).

trendshift.io 홈페이지의 "Trending // Daily" 카드 25건을 파싱한다. `/api/`는
robots.txt로 금지돼 있고 페이지는 SSR HTML이라 홈페이지를 그대로 읽는다.

아이템은 `source: "github"`로 만든다 — URL이 github.com 저장소라 dedup 1단에서
GitHub 트렌딩 항목과 합쳐지고, 스타 증가량(Δ)·예약석·화면 Δ 표시가 그대로
적용된다. 출처 라벨은 `feed`("Trendshift")로 구분된다.

카드 구조 (2026-09-05 실측):
  <a href="/repositories/<id>">owner/repo</a> … <span>442</span> … <p>설명</p>
  … <button><span>Like owner/repo, 0 likes</span></button>
같은 링크가 "Live // Mentions" 블록에도 나오는데 거기엔 Like 버튼이 없다.

OSS Insight는 붙이지 않았다 — /v1/trends/repos 가 2026-03-01부터
data_quality=unavailable(이벤트 수집률 0.3%)로 빈 결과만 돌려준다.
"""
from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

URL = "https://trendshift.io/"
FEED_NAME = "Trendshift"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

_NAME_RE = re.compile(r"^[\w.-]+/[\w.-]+$")
_DIGITS_RE = re.compile(r"^\d[\d,]*$")


def _card_of(anchor, name: str):
    """링크에서 위로 올라가 "Like <이 저장소>" 버튼을 품은 가장 가까운 조상을 찾는다.

    이름을 대조해야 한다 — mentions 블록의 링크는 자기 카드가 없어서 그냥 올라가면
    다른 저장소 카드들을 품은 상위 컨테이너를 카드로 오인한다.
    """
    want = f"Like {name}"
    node = anchor
    for _ in range(8):
        node = node.parent
        if node is None:
            return None
        if any(s.get_text(strip=True).startswith(want) for s in node.find_all("span")):
            return node
    return None


def _stars(card) -> int:
    for span in card.find_all("span"):
        txt = span.get_text(strip=True)
        if _DIGITS_RE.match(txt):
            return int(txt.replace(",", ""))
    return 0


def parse(html: str, limit: int = 25) -> list[dict]:
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    seen: set[str] = set()
    for a in soup.select('a[href^="/repositories/"]'):
        name = a.get_text(strip=True)
        if not _NAME_RE.match(name) or name in seen:
            continue
        card = _card_of(a, name)
        if card is None:
            continue
        seen.add(name)
        desc_tag = card.find("p")
        out.append({
            "title": name.replace("/", " / "),
            "url": f"https://github.com/{name}",
            "description": desc_tag.get_text(strip=True) if desc_tag else "",
            "source": "github",
            "feed": FEED_NAME,
            "upvotes": _stars(card),
            "comments": 0,
            "published_at": None,
        })
        if len(out) >= limit:
            break
    return out


def fetch(limit: int = 25) -> list[dict]:
    try:
        resp = requests.get(URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[trendshift] 요청 실패: {e}")
        return []
    return parse(resp.text, limit=limit)
