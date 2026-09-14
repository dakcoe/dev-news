import requests
from bs4 import BeautifulSoup

from news.core import http

TRENDING_URL = "https://github.com/trending"


def fetch(language: str = "", since: str = "daily") -> list[dict]:
    params = {"since": since}
    if language:
        params["l"] = language
    # 공용 http를 쓴다. 직접 requests를 부르면 5xx 재시도가 없어서, 순간 502 한
    # 번에 그 회차 GitHub 몫이 통째로 빈다. 예약석을 5개 잡고 있는 출처라 그
    # 자리가 비면 다른 출처로 메워지지도 않는다. 게다가 예외가 아니라 0건으로
    # 끝나서 출처 침묵 경고는 3회차 연속돼야 뜬다.
    try:
        resp = http.get(TRENDING_URL, params=params, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[github] 요청 실패: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    articles = []
    for repo in soup.select("article.Box-row"):
        title_tag = repo.select_one("h2 a")
        if not title_tag:
            continue
        href = title_tag.get("href", "").strip()
        url = f"https://github.com{href}"
        title = href.strip("/").replace("/", " / ")
        desc_tag = repo.select_one("p")
        description = desc_tag.get_text(strip=True) if desc_tag else ""
        stars_today_tag = repo.select_one("span.d-inline-block.float-sm-right")
        try:
            stars_today_text = stars_today_tag.get_text(strip=True) if stars_today_tag else "0"
            stars_today = int("".join(filter(str.isdigit, stars_today_text)) or "0")
        except ValueError:
            stars_today = 0
        articles.append({
            "title": title, "url": url, "description": description,
            "source": "github", "upvotes": stars_today, "comments": 0, "published_at": None,
        })
    return articles
