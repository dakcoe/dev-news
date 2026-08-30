from news.core import http

API_URL = "https://dev.to/api/articles"
DEFAULT_TAGS = ["javascript", "python", "ai", "webdev", "typescript", "rust", "go", "devops", "security", "programming"]


def fetch(tags: list[str] | None = None, per_tag: int = 10) -> list[dict]:
    if tags is None:
        tags = DEFAULT_TAGS

    seen_urls: set[str] = set()
    articles = []

    for tag in tags:
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
            continue

        for p in posts:
            url = p.get("url", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            articles.append({
                "title": p.get("title", ""),
                "url": url,
                "description": p.get("description", ""),
                "source": "devto",
                "tag": tag,
                "upvotes": p.get("positive_reactions_count", 0),
                "comments": p.get("comments_count", 0),
                "published_at": p.get("published_at"),
            })

    return articles
