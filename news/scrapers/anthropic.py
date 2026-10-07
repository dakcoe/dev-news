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

from news.core import common, http

BASE = "https://www.anthropic.com"
# (사이트, 목록 경로, 글 주소 접두사, 피드 이름)
PAGES = [
    (BASE, "/news", "/news/", "Anthropic"),
    (BASE, "/engineering", "/engineering/", "Anthropic Engineering"),
]
# Claude 제품 블로그는 RSS 가 없다(/blog/rss.xml 은 /resources/articles/rss.xml 로
# 넘어가 404). 2026-10 글 주소가 claude.com/blog/<slug> 에서 /resources/articles/<slug>
# 로 옮겨 가면서 사이트맵의 lastmod 가 없어져, 사이트맵에서 최근 글을 추리던 방식은
# 0건이 됐다. 목록 페이지는 서버 렌더링이고 최신순이며 카드마다 날짜와 제목이 있어
# 요청 한 번으로 끝난다(2026-10-07 실측 8건, 맨 위가 전날 글).
CLAUDE_BASE = "https://claude.com"
CLAUDE_LIST = ("/resources/articles", "Claude 블로그")
# 옛 주소로 걸린 카드도 받는다. 옮기는 도중이라 두 형식이 섞여 나올 수 있다.
CLAUDE_PREFIXES = ("/resources/articles/", "/blog/")
# 공용 http 의 Accept-Language 가 ko 라 그대로 보내면 /ko/resources/articles 로 307
# 되고, 링크가 전부 /ko/ 로 바뀌어 접두사에 하나도 안 걸린다(2026-10-07 실측 0건).
# 영어 원문 주소와 영어 날짜를 받으려고 이 요청만 영어로 묻는다.
CLAUDE_HEADERS = {"Accept-Language": "en-US,en;q=0.9"}
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
    """앵커 안의 텍스트를 줄 단위로 쪼개 제목과 날짜를 뽑는다.

    제목 태그(h1~h6)가 있으면 그것이 제목이다. 없을 때만 가장 긴 줄을 고른다 —
    카드에 설명이 붙으면 설명이 제목보다 길어서, engineering 맨 위 카드와
    claude.com 목록에서 설명문이 제목으로 들어갔다(2026-10-07).
    """
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
    heading = anchor.find(["h1", "h2", "h3", "h4", "h5", "h6"])
    if heading and heading.get_text(strip=True):
        return heading.get_text(" ", strip=True), published
    title = max(candidates, key=len) if candidates else ""
    return title, published


def _fetch_page(base: str, path: str, prefix: str | tuple[str, ...], feed: str, limit: int,
                require_date: bool = False, headers: dict | None = None) -> list[dict]:
    """require_date 면 날짜를 못 읽은 카드는 받지 않는다. 날짜 없는 글은 기간 필터를
    그냥 통과해 옛 글이 새 글처럼 실린다."""
    url = base + path
    prefixes = (prefix,) if isinstance(prefix, str) else prefix
    try:
        resp = http.get(url, timeout=15, headers=headers)
        resp.raise_for_status()
    except Exception as e:
        print(f"[anthropic] {url} 실패: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    seen: set[str] = set()
    out: list[dict] = []

    for anchor in soup.find_all("a", href=True):
        link = urljoin(base, anchor["href"])
        if not link.startswith(tuple(base + p for p in prefixes)):
            continue
        if link in seen or link.rstrip("/") == base + path.rstrip("/"):
            continue
        title, published = _parse_anchor(anchor)
        if not title or (require_date and published is None):
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


def _fetch_claude_blog(limit: int) -> list[dict]:
    path, feed = CLAUDE_LIST
    out = _fetch_page(CLAUDE_BASE, path, CLAUDE_PREFIXES, feed, limit,
                      require_date=True, headers=CLAUDE_HEADERS)
    for a in out:
        # 옮기기 전 주소로 이미 실린 글이 있다(claude-code-mods 등 seen.json 13건).
        # 같은 글을 가리키는 옛 주소를 origin_url 로 달면 중복 판정과 seen 이 둘 다
        # 본다 (core/dedup.url_keys). 긱뉴스가 원문 주소를 다는 것과 같은 자리다.
        old = a["url"].replace("/resources/articles/", "/blog/", 1)
        if old != a["url"]:
            a["origin_url"] = old
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
            **common.published(item.pubDate.get_text(strip=True) if item.pubDate else None),
        })
    print(f"[anthropic] {url} {len(out)}개")
    return out


def fetch(limit: int = 10, counts: dict[str, int] | None = None) -> list[dict]:
    """counts를 주면 하위 수집원별 건수를 `anthropic:피드이름`으로 남긴다.

    합계만 세면 수집원 하나가 0건이 돼도 anthropic 총계가 0이 아니라 출처 침묵
    경고가 안 뛴다. 2026-10 Claude 블로그가 사이트맵 형식 변경으로 0건이었는데
    총계는 24건이었다. rss 가 피드별로 세는 것과 같은 방식이다.
    """
    parts: list[tuple[str, list[dict]]] = []
    for base, path, prefix, feed in PAGES:
        parts.append((feed, _fetch_page(base, path, prefix, feed, limit)))
    parts.append((CLAUDE_LIST[1], _fetch_claude_blog(limit)))
    parts.append((DEV_RSS[1], _fetch_rss(*DEV_RSS, limit)))
    articles: list[dict] = []
    for feed, got in parts:
        articles.extend(got)
        if counts is not None:
            counts[f"anthropic:{feed}"] = len(got)
    if not articles:
        print("[anthropic] 0건 — 페이지 구조가 바뀐 것 같습니다. "
              "news/scrapers/anthropic.py 를 확인하세요.")
    return articles
