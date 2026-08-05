import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

HN_BASE = "https://hacker-news.firebaseio.com/v0"


def _fetch_item(item_id: int) -> dict | None:
    try:
        resp = requests.get(f"{HN_BASE}/item/{item_id}.json", timeout=5)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException:
        return None


def fetch(limit: int = 30) -> list[dict]:
    try:
        resp = requests.get(f"{HN_BASE}/topstories.json", timeout=10)
        resp.raise_for_status()
        top_ids = resp.json()[:limit]
    except requests.RequestException as e:
        print(f"[hackernews] topstories 요청 실패: {e}")
        return []

    articles = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(_fetch_item, id_): id_ for id_ in top_ids}
        for future in as_completed(futures):
            item = future.result()
            if not item or item.get("type") != "story":
                continue
            url = item.get("url") or f"https://news.ycombinator.com/item?id={item['id']}"
            text_html = item.get("text") or ""
            description = BeautifulSoup(text_html, "html.parser").get_text(separator=" ").strip()
            articles.append({
                "title": item.get("title", ""), "url": url, "description": description,
                "source": "hackernews", "upvotes": item.get("score", 0),
                "comments": item.get("descendants", 0), "published_at": item.get("time"),
            })
    return articles
