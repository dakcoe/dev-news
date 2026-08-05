"""범용 RSS/Atom 피드 스크래퍼.

config.yaml의 feeds 목록을 그대로 읽는다. 주소만 추가하면 소스가 늘어난다.

  feeds:
    - name: Anthropic
      url: https://www.anthropic.com/news/rss.xml
    - name: 카카오 기술블로그
      url: https://tech.kakao.com/feed/

name을 생략하면 도메인이 출처 이름이 된다.
피드 하나가 죽어도 나머지는 계속 수집한다.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "dev-news/1.0 (personal feed aggregator)"}


def _ts(value: str | None) -> float | None:
    if not value:
        return None
    for parser in (
        lambda v: parsedate_to_datetime(v),
        lambda v: datetime.fromisoformat(v.replace("Z", "+00:00")),
    ):
        try:
            dt = parser(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except Exception:
            continue
    return None


def _text(html: str, limit: int = 400) -> str:
    plain = BeautifulSoup(html or "", "html.parser").get_text(" ")
    return re.sub(r"\s+", " ", plain).strip()[:limit]


def _one(feed: dict, limit: int) -> list[dict]:
    url = feed["url"]
    name = feed.get("name") or urlparse(url).netloc.replace("www.", "")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[rss] {name} 실패: {e}")
        return []

    soup = BeautifulSoup(resp.content, "xml")
    entries = soup.find_all("item") or soup.find_all("entry")
    out = []
    for entry in entries[:limit]:
        title_tag = entry.find("title")
        title = title_tag.get_text(strip=True) if title_tag else ""

        link_tag = entry.find("link")
        link = ""
        if link_tag is not None:
            link = (link_tag.get_text(strip=True) or link_tag.get("href") or "").strip()
        if not title or not link:
            continue

        desc_tag = (entry.find("description") or entry.find("summary")
                    or entry.find("content") or entry.find("content:encoded"))
        pub_tag = (entry.find("pubDate") or entry.find("published")
                   or entry.find("updated") or entry.find("date"))

        out.append({
            "title": title,
            "url": link,
            "description": _text(desc_tag.get_text() if desc_tag else ""),
            "source": "rss",
            "feed": name,
            "upvotes": 0,
            "comments": 0,
            "published_at": _ts(pub_tag.get_text(strip=True) if pub_tag else None),
        })
    print(f"[rss] {name} {len(out)}개")
    return out


def fetch(feeds: list[dict] | None = None, per_feed: int = 8) -> list[dict]:
    if not feeds:
        return []
    articles: list[dict] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(_one, f, per_feed) for f in feeds if f.get("url")]
        for future in as_completed(futures):
            try:
                articles.extend(future.result())
            except Exception as e:
                print(f"[rss] 오류: {e}")
    return articles
