"""Reddit 스크래퍼 (기본 비활성).

비인증 hot.json은 대부분 403(Blocked)이 난다. 그래서 순서대로 시도한다.

  1) OAuth  — .env에 REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET 가 있으면 이 경로
  2) RSS    — 키가 없으면 공개 .rss 시도 (막힐 때도 있다)
  3) 포기   — 둘 다 실패하면 빈 리스트. 파이프라인은 계속 진행된다.

OAuth 키 만들기 (무료, 2분)
  https://www.reddit.com/prefs/apps → create app → 타입 "script"
  redirect uri는 http://localhost:8080 아무거나
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from email.utils import parsedate_to_datetime

import requests
from bs4 import BeautifulSoup

DEFAULT_SUBREDDITS = ["LocalLLaMA", "ClaudeAI", "MachineLearning", "programming", "singularity"]

UA = os.environ.get("REDDIT_USER_AGENT", "windows:dev-news:v1.0 (personal news aggregator)")
HEADERS = {"User-Agent": UA}

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
OAUTH_BASE = "https://oauth.reddit.com"


def _get_token() -> str | None:
    cid = os.environ.get("REDDIT_CLIENT_ID")
    secret = os.environ.get("REDDIT_CLIENT_SECRET")
    if not cid or not secret:
        return None
    try:
        resp = requests.post(
            TOKEN_URL, auth=(cid, secret),
            data={"grant_type": "client_credentials"},
            headers=HEADERS, timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("access_token")
    except requests.RequestException as e:
        print(f"[reddit] 토큰 발급 실패: {e}")
        return None


def _fetch_oauth(subreddit: str, token: str, limit: int) -> list[dict]:
    resp = requests.get(
        f"{OAUTH_BASE}/r/{subreddit}/hot",
        headers={**HEADERS, "Authorization": f"bearer {token}"},
        params={"limit": limit, "raw_json": 1}, timeout=15,
    )
    resp.raise_for_status()
    out = []
    for child in resp.json()["data"]["children"]:
        p = child["data"]
        if p.get("stickied") or p.get("is_meta"):
            continue
        url = p.get("url") or ""
        if not url or "reddit.com" in url:
            url = "https://www.reddit.com" + p["permalink"]
        out.append({
            "title": p.get("title", ""), "url": url,
            "description": (p.get("selftext") or "")[:300].strip(),
            "source": "reddit", "subreddit": subreddit,
            "upvotes": p.get("score", 0), "comments": p.get("num_comments", 0),
            "published_at": p.get("created_utc"),
        })
    return out


def _fetch_rss(subreddit: str, limit: int) -> list[dict]:
    resp = requests.get(
        f"https://www.reddit.com/r/{subreddit}/hot.rss",
        headers=HEADERS, params={"limit": limit}, timeout=15,
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "xml")
    out = []
    for entry in soup.find_all("entry")[:limit]:
        title = entry.title.get_text(strip=True) if entry.title else ""
        link_tag = entry.find("link")
        url = (link_tag.get("href") if link_tag else "") or ""
        if not title or not url:
            continue
        content = entry.find("content")
        text = BeautifulSoup(content.get_text() if content else "", "html.parser").get_text(" ")
        pub = entry.find("published") or entry.find("updated")
        ts = None
        if pub:
            raw = pub.get_text(strip=True)
            try:
                ts = datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
            except ValueError:
                try:
                    ts = parsedate_to_datetime(raw).timestamp()
                except Exception:
                    ts = None
        out.append({
            "title": title, "url": url,
            "description": re.sub(r"\s+", " ", text).strip()[:300],
            "source": "reddit", "subreddit": subreddit,
            "upvotes": 0, "comments": 0, "published_at": ts,
        })
    return out


def fetch(subreddits: list[str] | None = None, limit: int = 15) -> list[dict]:
    subreddits = subreddits or DEFAULT_SUBREDDITS
    token = _get_token()
    print(f"[reddit] {'OAuth' if token else 'RSS'} 방식으로 시도")

    articles: list[dict] = []
    blocked = 0
    for sub in subreddits:
        try:
            articles.extend(_fetch_oauth(sub, token, limit) if token else _fetch_rss(sub, limit))
        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else "?"
            if code in (401, 403, 429):
                blocked += 1
            print(f"[reddit] r/{sub} 실패(HTTP {code})")
        except Exception as e:
            print(f"[reddit] r/{sub} 실패: {e}")

    if not articles and blocked:
        print("[reddit] 전부 차단됨 — .env에 REDDIT_CLIENT_ID/SECRET을 넣거나 "
              "config.yaml에서 reddit: false 로 두세요.")
    return articles
