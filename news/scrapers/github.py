import requests
from bs4 import BeautifulSoup

TRENDING_URL = "https://github.com/trending"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


def fetch(language: str = "", since: str = "daily") -> list[dict]:
    params = {"since": since}
    if language:
        params["l"] = language
    try:
        resp = requests.get(TRENDING_URL, headers=HEADERS, params=params, timeout=10)
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
