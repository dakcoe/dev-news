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

import requests
from bs4 import BeautifulSoup

BASE = "https://www.anthropic.com"
PAGES = [
    ("/news", "/news/"),
    ("/engineering", "/engineering/"),
]
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

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
    lines = [l.strip() for l in anchor.get_text("\n").split("\n") if l.strip()]
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


def _fetch_page(path: str, prefix: str, limit: int) -> list[dict]:
    url = BASE + path
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[anthropic] {path} 실패: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    seen: set[str] = set()
    out: list[dict] = []

    for anchor in soup.select(f'a[href^="{prefix}"]'):
        href = anchor.get("href", "")
        link = urljoin(BASE, href)
        if link in seen or link.rstrip("/") == BASE + path:
            continue
        title, published = _parse_anchor(anchor)
        if not title:
            continue
        seen.add(link)
        out.append({
            "title": title,
            "url": link,
            "description": "",
            "source": "anthropic",
            "feed": "Anthropic" + (" Engineering" if "engineering" in prefix else ""),
            "upvotes": 0,
            "comments": 0,
            "published_at": published,
        })
        if len(out) >= limit:
            break

    print(f"[anthropic] {path} {len(out)}개")
    return out


def fetch(limit: int = 10) -> list[dict]:
    articles: list[dict] = []
    for path, prefix in PAGES:
        articles.extend(_fetch_page(path, prefix, limit))
    if not articles:
        print("[anthropic] 0건 — 페이지 구조가 바뀐 것 같습니다. "
              "news/scrapers/anthropic.py 를 확인하세요.")
    return articles
