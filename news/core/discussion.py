"""본문을 못 가져온 기사를 그 글에 달린 댓글로 메운다.

왜 필요한가. 9월 한 달 882건 중 69건(8%)이 요약 없이 실렸고, 그중 43건은
화면에 "(본문이 공개되지 않은 기사 — 원문을 확인하세요)"만 떴다. 원인은 본문
추출 실패다 — 같은 주소를 집에서 받으면 멀쩡히 오는데(서브스택 22,600자,
digiato 3,931자) 깃허브 러너의 IP 는 여러 사이트가 막는다(403·429·연결 거부).
본문이 비면 요약 프롬프트가 "제목만으로 쓰되 추측하지 마라"가 되고, 모델은
지시대로 "없음"을 내놓는다. 그 결과가 빈 요약이다.

해커뉴스·Lobsters 글에는 독자 댓글이 있고, 그 API 는 러너에서도 막히지 않는다.
댓글은 기사가 아니지만, 무엇이 논의되는지는 알려 준다. 그래서 본문 대신
댓글을 넣고, 프롬프트와 화면에 "댓글을 바탕으로 썼다"고 밝힌다. 기사 내용을
단정하지 않게 하는 것은 프롬프트 쪽(summarizer._body_for_prompt)이 맡는다.

댓글도 없으면 그대로 둔다 — 그 경우는 지금처럼 자리표시가 뜬다.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, quote, urlparse

from bs4 import BeautifulSoup

from news.core import http

HN_ITEM = "https://hacker-news.firebaseio.com/v0/item/{}.json"
HN_SEARCH = "https://hn.algolia.com/api/v1/search?query={}&restrictSearchableAttributes=url&hitsPerPage=1"
MAX_COMMENTS = 3          # 위에서부터 — 해커뉴스·Lobsters 둘 다 순위순으로 준다
MAX_EACH = 600            # 댓글 하나 글자 수
MAX_TOTAL = 1800          # 프롬프트가 본문을 2,000자에서 자르므로 그 안쪽


def _plain(html_or_text: str) -> str:
    text = BeautifulSoup(html_or_text or "", "html.parser").get_text(separator=" ")
    return re.sub(r"\s+", " ", text).strip()


def _hn_id(article: dict) -> str | None:
    """저장된 토론 주소에서 글 번호를 꺼낸다. 없으면 주소로 검색한다."""
    disc = article.get("discussion") or ""
    if "news.ycombinator.com/item" in disc:
        return (parse_qs(urlparse(disc).query).get("id") or [None])[0]
    if article.get("source") != "hackernews":
        return None
    try:
        hits = http.get(HN_SEARCH.format(quote(article["url"], safe="")), timeout=10).json().get("hits") or []
        return str(hits[0]["objectID"]) if hits else None
    except Exception:
        return None


def _hn_comments(item_id: str) -> list[str]:
    try:
        kids = (http.get(HN_ITEM.format(item_id), timeout=10).json() or {}).get("kids") or []
    except Exception:
        return []
    out = []
    for kid in kids[:MAX_COMMENTS * 2]:      # 지워진 댓글이 섞여 있어 조금 더 본다
        try:
            c = http.get(HN_ITEM.format(kid), timeout=10).json() or {}
        except Exception:
            continue
        if c.get("deleted") or c.get("dead") or not c.get("text"):
            continue
        out.append(_plain(c["text"]))
        if len(out) >= MAX_COMMENTS:
            break
    return out


def _lobsters_comments(article: dict) -> list[str]:
    disc = article.get("discussion") or ""
    if "lobste.rs/s/" not in disc:
        return []
    try:
        data = http.get(disc.rstrip("/") + ".json", timeout=10).json() or {}
    except Exception:
        return []
    out = []
    for c in data.get("comments") or []:
        text = _plain(c.get("comment_plain") or c.get("comment") or "")
        if text:
            out.append(text)
        if len(out) >= MAX_COMMENTS:
            break
    return out


def comments_for(article: dict) -> list[str]:
    if article.get("source") == "lobsters":
        return _lobsters_comments(article)
    item_id = _hn_id(article)
    return _hn_comments(item_id) if item_id else []


def _pack(comments: list[str]) -> str:
    parts, total = [], 0
    for i, c in enumerate(comments, 1):
        c = c[:MAX_EACH]
        if total + len(c) > MAX_TOTAL:
            break
        parts.append(f"[댓글 {i}] {c}")
        total += len(c)
    return "\n\n".join(parts)


def fill_from_discussion(articles: list[dict]) -> list[dict]:
    """content 가 빈 기사에 댓글을 채운다. 채운 기사는 body_from='comments'."""
    out, filled = [], 0
    for a in articles:
        if (a.get("content") or "").strip():
            out.append(a)
            continue
        packed = _pack(comments_for(a))
        if packed:
            out.append({**a, "content": packed, "body_from": "comments"})
            filled += 1
        else:
            out.append(a)
    if filled:
        print(f"[discussion] 본문 대신 댓글로 채움 {filled}건")
    return out
