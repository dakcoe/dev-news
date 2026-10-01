"""Anthropic 뉴스·엔지니어링 블로그 스크래퍼.

Anthropic은 RSS를 제공하지 않는다(news/rss.xml, rss.xml 모두 404).
다만 목록 페이지가 서버 렌더링이라 제목과 날짜가 HTML에 그대로 들어 있어 파싱이 가능하다.

목록 페이지 구조가 바뀌면 0건이 될 수 있으므로, 그때는 PAGES의 셀렉터 대신
아래 _parse_anchor 의 규칙(앵커 텍스트 줄 단위 파싱)만 손보면 된다.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from news.core import http
from news.core.common import to_timestamp

BASE = "https://www.anthropic.com"
# (사이트, 목록 경로, 글 주소 접두사, 피드 이름, 제목을 담은 속성 — 없으면 앵커 글자)
# Claude 제품 블로그(claude.com/blog)는 2026-10 기준 RSS 가 없고, 목록 카드에 글자 대신
# data-cta-copy 속성으로 제목이 들어 있다. 날짜는 목록에 없다 — 첫 화면의 최신 글만 받고
# 한 번 실린 글은 seen 이 막는다.
PAGES = [
    (BASE, "/news", "/news/", "Anthropic", None),
    (BASE, "/engineering", "/engineering/", "Anthropic Engineering", None),
    ("https://claude.com", "/blog", "/blog/", "Claude 블로그", "data-cta-copy"),
]
# Claude 개발자 블로그는 RSS 가 있다. 개발자용 글(새 모델로 개발하기, Claude Code 사용법)이
# 여기에만 올라와서, 빠뜨리면 HN 에 누가 올려야만 실렸다 (2026-10-02 사용자 지적).
DEV_RSS = ("https://claude.dev/rss.xml", "Claude 개발자 블로그")

# "Aug 4, 2026" / "August 4, 2026" / "2026-08-04"
DATE_PATTERNS = [
    (re.compile(r"^([A-Z][a-z]{2,8})\s+(\d{1,2}),\s*(\d{4})$"), "%b %d %Y"),
    (re.compile(r"^(\d{4})-(\d{2})-(\d{2})$"), "%Y-%m-%d"),
]

SKIP_TITLES = {"news", "engineering", "read more", "all posts", "announcements"}


def _parse_date(text: str) -> float | None:
    text = text.strip()
    for pattern, fmt in DATE_PATTERNS:
        m = pattern.match(text)
        if not m:
            continue
        try:
            if fmt == "%Y-%m-%d":
                dt = datetime.strptime(text, "%Y-%m-%d")
            else:
                month = m.group(1)[:3]
                dt = datetime.strptime(f"{month} {m.group(2)} {m.group(3)}", "%b %d %Y")
            return dt.replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    return None


def _parse_anchor(anchor) -> tuple[str, float | None]:
    """앵커 안의 텍스트를 줄 단위로 쪼개 제목과 날짜를 뽑는다."""
    lines = [ln.strip() for ln in anchor.get_text("\n").split("\n") if ln.strip()]
    published = None
    candidates = []
    for line in lines:
        ts = _parse_date(line)
        if ts is not None:
            published = ts
            continue
        if line.lower() in SKIP_TITLES or len(line) < 8:
            continue
        candidates.append(line)
    title = max(candidates, key=len) if candidates else ""
    return title, published


def _fetch_page(base: str, path: str, prefix: str, feed: str, title_attr: str | None,
                limit: int) -> list[dict]:
    url = base + path
    try:
        resp = http.get(url, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"[anthropic] {url} 실패: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    seen: set[str] = set()
    out: list[dict] = []

    for anchor in soup.select(f'a[href^="{prefix}"]'):
        href = anchor.get("href", "")
        link = urljoin(base, href)
        if link in seen or link.rstrip("/") == base + path.rstrip("/"):
            continue
        if title_attr:
            title, published = (anchor.get(title_attr) or "").strip(), None
        else:
            title, published = _parse_anchor(anchor)
        if not title:
            continue
        seen.add(link)
        out.append({
            "title": title,
            "url": link,
            "description": "",
            "source": "anthropic",
            "feed": feed,
            "upvotes": 0,
            "comments": 0,
            "published_at": published,
        })
        if len(out) >= limit:
            break

    print(f"[anthropic] {url} {len(out)}개")
    return out


def _fetch_rss(url: str, feed: str, limit: int) -> list[dict]:
    try:
        resp = http.get(url, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"[anthropic] {url} 실패: {e}")
        return []
    out = []
    for item in BeautifulSoup(resp.text, "xml").find_all("item")[:limit]:
        title = item.title.get_text(strip=True) if item.title else ""
        link = item.link.get_text(strip=True) if item.link else ""
        if not title or not link:
            continue
        desc = item.find("description")
        out.append({
            "title": title,
            "url": link,
            "description": BeautifulSoup(desc.get_text() if desc else "", "html.parser").get_text(" ").strip()[:500],
            "source": "anthropic",
            "feed": feed,
            "upvotes": 0,
            "comments": 0,
            "published_at": to_timestamp(item.pubDate.get_text(strip=True) if item.pubDate else None),
        })
    print(f"[anthropic] {url} {len(out)}개")
    return out


def fetch(limit: int = 10) -> list[dict]:
    articles: list[dict] = []
    for base, path, prefix, feed, title_attr in PAGES:
        articles.extend(_fetch_page(base, path, prefix, feed, title_attr, limit))
    articles.extend(_fetch_rss(*DEV_RSS, limit))
    if not articles:
        print("[anthropic] 0건 — 페이지 구조가 바뀐 것 같습니다. "
              "news/scrapers/anthropic.py 를 확인하세요.")
    return articles
