import requests

from news.core.common import to_timestamp

URL = "https://lobste.rs/hottest.json"
HEADERS = {"User-Agent": "news-scraper/1.0 (personal feed aggregator)"}


def fetch(limit: int = 25) -> list[dict]:
    try:
        resp = requests.get(URL, headers=HEADERS, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[lobsters] 요청 실패: {e}")
        return []

    articles = []
    for item in resp.json()[:limit]:
        published_at = to_timestamp(item.get("created_at"))
        articles.append({
            "title": item.get("title", ""),
            "url": item.get("url") or item.get("comments_url", ""),
            "description": item.get("description_plain", "")[:500],
            "source": "lobsters", "upvotes": item.get("score", 0),
            "comments": item.get("comment_count", 0), "published_at": published_at,
        })
    return articles
