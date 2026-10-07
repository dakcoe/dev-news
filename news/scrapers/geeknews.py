"""긱뉴스(news.hada.io) 스크래퍼.

공식 RSS 주소가 바뀐 전례가 있어 후보를 순서대로 시도한다.
전부 실패하면 빈 리스트를 반환하고 파이프라인은 계속 진행된다.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from news.core import http
from news.core.common import published

FEED_CANDIDATES = [
    "https://news.hada.io/rss/news",
    "https://feeds.feedburner.com/geeknews-feed",
]

def _clean(html: str) -> str:
    text = BeautifulSoup(html or "", "html.parser").get_text(" ").strip()
    return re.sub(r"\s+", " ", text)[:500]


def origin_url(topic_url: str) -> str | None:
    """긱뉴스 글이 소개하는 원문 주소. 못 찾으면 None.

    피드의 <link>는 긱뉴스 글 주소라, 같은 원문을 해커뉴스가 물어와도 주소로는
    같은 기사인지 알 수 없다. 한국어 제목과 영어 제목은 낱말도 안 겹쳐서 제목
    비교로도 못 잡는다 — 2026-09-22~23 네 회차에서 같은 소식이 두 줄로 실린
    9쌍 중 6쌍이 이 경우였다. 글 페이지의 제목 링크가 원문이다.
    """
    try:
        return _read_origin(topic_url)
    except Exception:
        return None


def _read_origin(topic_url: str) -> str | None:
    """origin_url 과 같되 요청 실패를 예외로 올린다. fetch 가 차단을 알아보려고 쓴다."""
    resp = http.get(topic_url, timeout=10)
    resp.raise_for_status()
    a = BeautifulSoup(resp.text, "html.parser").select_one("a.topic-title-link[href]")
    href = (a["href"] if a else "").strip()
    # Show GN 처럼 원문이 없는 글은 제목 링크가 긱뉴스 자신을 가리킨다
    host = urlparse(href).hostname or ""
    if not href.startswith(("http://", "https://")) or host.endswith("hada.io"):
        return None
    return href


def _status(e: Exception) -> int | None:
    return getattr(getattr(e, "response", None), "status_code", None)


def _attach_origins(articles: list[dict]) -> int:
    """원문 주소를 달고 찾은 수를 돌려준다.

    2026-09-30부터 글 페이지가 브라우저가 아닌 요청에 전부 403이다. 피드·robots.txt
    는 200이고, 응답이 CloudFront 함수가 만든 "Forbidden" 이라 사이트가 일부러 막은
    것이다(robots.txt 는 허용). 피드에는 원문 링크가 없고, 브라우저 위장은 하지
    않는다(core/http.py). 그래서 첫 요청이 403이면 나머지는 묻지 않는다 — 회차마다
    30번 막히는 요청을 보낼 이유가 없다. 찾은 수는 fetch 가 출처 건수로 남겨,
    연속 0건이면 출처 침묵 알림으로 드러난다.
    """
    if not articles:
        return 0
    first, rest = articles[0], articles[1:]
    failed = 0
    try:
        origin = _read_origin(first["url"])
    except Exception as e:
        if _status(e) == 403:
            print(f"[geeknews] 글 페이지가 403으로 막혀 원문 주소를 못 찾음 — "
                  f"나머지 {len(rest)}건은 묻지 않는다")
            return 0
        print(f"[geeknews] 원문 주소 못 읽음 {first['url']}: {e}")
        origin, failed = None, 1
    if origin:
        first["origin_url"] = origin

    def one(a):
        try:
            return _read_origin(a["url"]), None
        except Exception as e:
            return None, e

    with ThreadPoolExecutor(max_workers=6) as pool:
        for a, (origin, err) in zip(rest, pool.map(one, rest)):
            if err is not None:
                failed += 1
            elif origin:
                a["origin_url"] = origin
    if failed:
        print(f"[geeknews] 원문 주소 요청 {len(rest) + 1}건 중 {failed}건 실패")
    return sum(1 for a in articles if a.get("origin_url"))


def fetch(limit: int = 25, counts: dict[str, int] | None = None) -> list[dict]:
    """counts를 주면 원문 주소를 찾은 기사 수를 `geeknews:원문`으로 남긴다."""
    body = None
    for url in FEED_CANDIDATES:
        try:
            resp = http.get(url, timeout=10)
            resp.raise_for_status()
            if "<item" in resp.text or "<entry" in resp.text:
                body = resp.text
                break
        except Exception as e:
            print(f"[geeknews] {url} 실패: {e}")
    if body is None:
        print("[geeknews] 사용 가능한 피드를 찾지 못했습니다")
        return []

    soup = BeautifulSoup(body, "xml")
    items = soup.find_all("item") or soup.find_all("entry")

    articles: list[dict] = []
    for item in items[:limit]:
        title = (item.title.get_text(strip=True) if item.title else "").strip()
        link_tag = item.find("link")
        if link_tag is None:
            continue
        url = (link_tag.get_text(strip=True) or link_tag.get("href") or "").strip()
        if not title or not url:
            continue
        desc_tag = item.find("description") or item.find("summary") or item.find("content")
        pub_tag = item.find("pubDate") or item.find("published") or item.find("updated")
        articles.append(
            {
                "title": title,
                "url": url,
                "description": _clean(desc_tag.get_text() if desc_tag else ""),
                "source": "geeknews",
                "upvotes": 0,
                "comments": 0,
                **published(pub_tag.get_text(strip=True) if pub_tag else None),
            }
        )
    # 기사 주소는 긱뉴스 글 그대로 둔다 — 한국어 소개글이 요약·원문 열기의 대상이다.
    # 원문 주소는 중복 판정과 seen 에만 쓴다 (core/dedup.py·core/seen.py).
    found = _attach_origins(articles)
    if counts is not None:
        counts["geeknews:원문"] = found
    return articles
