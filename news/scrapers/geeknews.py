"""긱뉴스(news.hada.io) 스크래퍼.

공식 RSS 주소가 바뀐 전례가 있어 후보를 순서대로 시도한다.
전부 실패하면 빈 리스트를 반환하고 파이프라인은 계속 진행된다.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from news.core import http
from news.core.common import to_timestamp

FEED_CANDIDATES = [
    "https://news.hada.io/rss/news",
    "https://feeds.feedburner.com/geeknews-feed",
]

def _clean(html: str) -> str:
    text = BeautifulSoup(html or "", "html.parser").get_text(" ").strip()
    return re.sub(r"\s+", " ", text)[:500]


def fetch(limit: int = 25) -> list[dict]:
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
        published = item.find("pubDate") or item.find("published") or item.find("updated")
        articles.append(
            {
                "title": title,
                "url": url,
                "description": _clean(desc_tag.get_text() if desc_tag else ""),
                "source": "geeknews",
                "upvotes": 0,
                "comments": 0,
                "published_at": to_timestamp(published.get_text(strip=True) if published else None),
            }
        )
    return articles
