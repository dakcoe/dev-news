from concurrent.futures import ThreadPoolExecutor

from news.core import http

API_URL = "https://dev.to/api/articles"
DEFAULT_TAGS = ["javascript", "python", "ai", "webdev", "typescript", "rust", "go", "devops", "security", "programming"]


def _one(tag: str, per_tag: int) -> list[dict]:
    try:
        resp = http.get(
            API_URL,
            params={"tag": tag, "per_page": per_tag, "state": "rising"},
            timeout=10,
        )
        resp.raise_for_status()
        posts = resp.json()
    except Exception as e:
        print(f"[devto] tag={tag} 오류: {e}")
        return []

    out = []
    for p in posts:
        url = p.get("url", "")
        if not url:
            continue
        out.append({
            "title": p.get("title", ""),
            "url": url,
            "description": p.get("description", ""),
            "source": "devto",
            "tag": tag,
            "upvotes": p.get("positive_reactions_count", 0),
            "comments": p.get("comments_count", 0),
            "published_at": p.get("published_at"),
        })
    return out


def fetch(tags: list[str] | None = None, per_tag: int = 10) -> list[dict]:
    """태그를 나란히 받는다.

    직렬로 돌면 한 태그가 막힐 때 최악이 63초(재시도 3회 + 백오프)이고, 태그가
    10개라 혼자 10분을 먹는다. 워크플로 제한이 25분이라 본문 추출·요약까지
    더하면 회차가 취소될 수 있다 — 그러면 커밋이 없어 사이트가 조용히 낡는다.
    평소에는 직렬로도 6초면 끝나므로, 이건 최악의 경우를 자르는 장치다.

    동시 요청은 4개로 묶는다. 한 사이트를 두드리는 일이라 rss(피드 10곳에 6개)
    보다 절제한다.

    태그 순서는 유지한다 — 같은 글이 여러 태그에 걸릴 때 어느 태그로 기록되는지가
    회차마다 달라지면 안 된다.
    """
    if tags is None:
        tags = DEFAULT_TAGS

    seen_urls: set[str] = set()
    articles: list[dict] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for got in pool.map(lambda t: _one(t, per_tag), tags):
            for a in got:
                if a["url"] in seen_urls:
                    continue
                seen_urls.add(a["url"])
                articles.append(a)
    return articles
