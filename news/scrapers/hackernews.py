from bs4 import BeautifulSoup

from news.core import http
from concurrent.futures import ThreadPoolExecutor, as_completed

HN_BASE = "https://hacker-news.firebaseio.com/v0"


def _fetch_item(item_id: int) -> dict | None:
    try:
        resp = http.get(f"{HN_BASE}/item/{item_id}.json", timeout=10)
        resp.raise_for_status()
        return resp.json() or {}      # 지워진 글은 null 이다 — 실패와 구분한다
    except Exception:
        return None


def fetch(limit: int = 30) -> list[dict]:
    try:
        resp = http.get(f"{HN_BASE}/topstories.json", timeout=10)
        resp.raise_for_status()
        top_ids = resp.json()[:limit]
    except Exception as e:
        print(f"[hackernews] topstories 요청 실패: {e}")
        return []

    articles = []
    failed = 0
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(_fetch_item, id_): id_ for id_ in top_ids}
        for future in as_completed(futures):
            item = future.result()
            # None 은 요청 실패다. 하나씩은 흔하지만 몇 건이 빠졌는지 남겨 둬야
            # 해커뉴스 몫이 줄어든 회차의 원인을 알 수 있다.
            if item is None:
                failed += 1
                continue
            if item.get("type") != "story":
                continue
            url = item.get("url") or f"https://news.ycombinator.com/item?id={item['id']}"
            text_html = item.get("text") or ""
            description = BeautifulSoup(text_html, "html.parser").get_text(separator=" ").strip()
            articles.append({
                "title": item.get("title", ""), "url": url, "description": description,
                "source": "hackernews", "upvotes": item.get("score", 0),
                "comments": item.get("descendants", 0), "published_at": item.get("time"),
                # 본문을 못 가져왔을 때 댓글을 대신 넣으려고 남긴다 (core/discussion.py)
                "discussion": f"https://news.ycombinator.com/item?id={item['id']}",
            })
    if failed:
        print(f"[hackernews] 글 {len(top_ids)}건 중 {failed}건 요청 실패")
    return articles
