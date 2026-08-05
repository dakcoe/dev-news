"""기사 본문과 대표 이미지(og:image)를 함께 수집한다.

봇의 news/core/fetcher.py를 확장한 버전 — 본문만이 아니라 썸네일도 뽑는다.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin

import requests
import trafilatura
from bs4 import BeautifulSoup

MAX_CONTENT_CHARS = 3000
MIN_CONTENT_CHARS = 200

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

GITHUB_REPO_RE = re.compile(r"^https?://github\.com/([^/]+)/([^/?#]+?)(?:\.git)?(?:[/?#].*)?$")


def _github_readme(owner: str, repo: str) -> str | None:
    for filename in ("README.md", "readme.md", "README.rst", "README"):
        url = f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/{filename}"
        try:
            resp = requests.get(url, timeout=10, headers=HEADERS)
            if resp.status_code == 200 and len(resp.text.strip()) >= MIN_CONTENT_CHARS:
                return resp.text.strip()[:MAX_CONTENT_CHARS]
        except requests.RequestException:
            pass
    return None


def _og_image(soup: BeautifulSoup, base_url: str) -> str | None:
    for attrs in (
        {"property": "og:image"},
        {"name": "og:image"},
        {"name": "twitter:image"},
        {"property": "twitter:image"},
    ):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            src = tag["content"].strip()
            if src.startswith("//"):
                return "https:" + src
            if src.startswith("/"):
                return urljoin(base_url, src)
            if src.startswith("http"):
                return src
    return None


def _fetch_one(url: str) -> tuple[str | None, str | None]:
    """(본문, 썸네일 URL)"""
    m = GITHUB_REPO_RE.match(url)
    if m:
        owner, repo = m.group(1), m.group(2)
        readme = _github_readme(owner, repo)
        return readme, f"https://opengraph.githubassets.com/1/{owner}/{repo}"

    try:
        resp = requests.get(url, timeout=15, headers=HEADERS)
        resp.raise_for_status()
        html = resp.text
    except requests.RequestException:
        return None, None

    content = None
    try:
        text = trafilatura.extract(html, include_comments=False, include_tables=False)
        if text and len(text) >= MIN_CONTENT_CHARS:
            content = text[:MAX_CONTENT_CHARS]
    except Exception:
        pass

    image = None
    try:
        image = _og_image(BeautifulSoup(html, "html.parser"), resp.url)
    except Exception:
        pass

    return content, image


def enrich(articles: list[dict], max_workers: int = 5) -> list[dict]:
    results: dict[str, tuple[str | None, str | None]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch_one, a["url"]): a["url"] for a in articles}
        for future in as_completed(futures):
            url = futures[future]
            try:
                results[url] = future.result()
            except Exception:
                results[url] = (None, None)

    got_text = sum(1 for c, _ in results.values() if c)
    got_img = sum(1 for _, i in results.values() if i)
    print(f"[enrich] 본문 {got_text}/{len(articles)} · 썸네일 {got_img}/{len(articles)}")

    out = []
    for a in articles:
        content, image = results.get(a["url"], (None, None))
        out.append({**a, "content": content, "image": image})
    return out
