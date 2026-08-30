"""기사 본문과 대표 이미지(og:image)를 함께 수집한다.

봇의 news/core/fetcher.py를 확장한 버전 — 본문만이 아니라 썸네일도 뽑는다.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin

import trafilatura
from bs4 import BeautifulSoup

from news.api_health import _error_kind, classify
from news.core import http
from news.core.fetch_health import reason_of, record

MAX_CONTENT_CHARS = 3000
MIN_CONTENT_CHARS = 80

GITHUB_REPO_RE = re.compile(r"^https?://github\.com/([^/]+)/([^/?#]+?)(?:\.git)?(?:[/?#].*)?$")


def usable_content(text, description=None):
    """추출한 본문을 쓸지 결정한다.

    바닥값(MIN_CONTENT_CHARS)은 쿠키 배너·내비게이션 같은 껍데기를 막는 역할만
    한다. 예전 값 200은 멀쩡한 짧은 글까지 버렸다 — mastodon 툿 136자,
    data4sci 119자가 그렇게 사라져 요약이 통째로 비었다. 짧은 글은 원래 짧은
    것이지 추출 실패가 아니다.

    description보다 짧으면 쓰지 않는다. summarizer가 `content or description`
    순으로 고르기 때문에, 그냥 두면 85자 본문이 400자 description을 밀어낸다.
    """
    if not text:
        return None
    text = text.strip()
    if len(text) < MIN_CONTENT_CHARS:
        return None
    if description and len(text) <= len(description.strip()):
        return None
    return text[:MAX_CONTENT_CHARS]


def _github_readme(owner: str, repo: str) -> str | None:
    for filename in ("README.md", "readme.md", "README.rst", "README"):
        url = f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/{filename}"
        try:
            resp = http.get(url, timeout=10)
            if resp.status_code == 200 and len(resp.text.strip()) >= MIN_CONTENT_CHARS:
                return resp.text.strip()[:MAX_CONTENT_CHARS]
        except Exception:
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


def _fetch_one(url: str) -> tuple[str | None, str | None, str | None, int | None]:
    """(본문, 썸네일 URL, 링크 판정, 응답 코드)

    판정은 api_health.classify()를 그대로 쓴다 — 같은 문제를 이미 실측으로
    다듬어 놨다. 404·410은 dead, 5xx·타임아웃은 unknown, 403·429는 ok다.
    403을 죽음으로 세면 봇 차단된 멀쩡한 기사를 잃는다(실측 4건).
    """
    m = GITHUB_REPO_RE.match(url)
    if m:
        # 저장소 링크는 raw README로 우회한다. README가 없어 404가 나도 저장소는
        # 멀쩡하므로 판정 대상이 아니다.
        owner, repo = m.group(1), m.group(2)
        readme = _github_readme(owner, repo)
        return readme, f"https://opengraph.githubassets.com/1/{owner}/{repo}", None, None

    try:
        resp = http.get(url, timeout=15)
    except Exception as e:
        return None, None, classify(None, _error_kind(e)), None

    status = classify(resp.status_code, None)
    if status != "ok":
        return None, None, status, resp.status_code

    # HTML이 아니면 본문 추출 대상이 아니다. 전에는 PDF·이미지도 그대로
    # trafilatura에 들어갔다.
    ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
    if ctype and "html" not in ctype and "xml" not in ctype:
        return None, None, status, resp.status_code

    # bytes를 넘긴다. resp.text는 헤더에 charset이 없으면 ISO-8859-1로 추정해
    # HTML meta에만 UTF-8을 선언한 한국어 블로그의 본문이 깨진다.
    html = resp.content

    content = None
    try:
        content = trafilatura.extract(html, include_comments=False, include_tables=False)
    except Exception:
        pass

    image = None
    try:
        image = _og_image(BeautifulSoup(html, "html.parser"), resp.url)
    except Exception:
        pass

    return content, image, status, resp.status_code


def enrich(articles: list[dict], max_workers: int = 5) -> list[dict]:
    results: dict[str, tuple] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch_one, a["url"]): a["url"] for a in articles}
        for future in as_completed(futures):
            url = futures[future]
            try:
                results[url] = future.result()
            except Exception:
                results[url] = (None, None, None, None)

    # 채택 기준(usable_content)을 통과한 것만 센다 — 원시 추출본 수와 다르다
    got_text = 0
    got_img = sum(1 for _, i, _, _ in results.values() if i)
    dead = sum(1 for _, _, s, _ in results.values() if s == "dead")

    out = []
    rows: list[dict] = []
    for a in articles:
        raw, image, status, code = results.get(a["url"], (None, None, None, None))
        content = usable_content(raw, a.get("description"))
        if content:
            got_text += 1
        rows.append({"url": a["url"], "source": a.get("source", ""),
                     "reason": reason_of(status, code, raw, accepted=bool(content))})
        out.append({**a, "content": content, "image": image, "link_status": status})

    print(f"[enrich] 본문 {got_text}/{len(articles)} · 썸네일 {got_img}/{len(articles)}"
          + (f" · 죽은 링크 {dead}" if dead else ""))
    record(rows)
    return out
