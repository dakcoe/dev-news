"""robots.txt 확인 (respect-robots).

기사 본문은 남의 사이트에서 받아 요약 재료로 쓴다. 사이트가 robots.txt 로 막은
페이지는 받지 않는다. 2026-10 게재 기사 862건 중 13건이 그런 페이지였다
(twitter.com 3 · lobste.rs 2 · linkedin 1 등).

판정은 RFC 9309 를 따른다. 가장 긴 규칙이 이기고, 길이가 같으면 Allow 가 이기며,
`*` 와 끝의 `$` 를 읽는다. 표준 라이브러리 urllib.robotparser 는 와일드카드를
글자 그대로 비교한다 — github.com 의 `Disallow: /*?since=*` 를 못 읽고
/trending?since=daily 를 허용으로 본다.

robots.txt 응답별 처리 (RFC 9309 2.3.1):
  2xx                규칙대로
  4xx (429 제외)     파일이 없는 것으로 보고 전부 허용
  429·5xx·연결 실패  전부 금지 — 그 회차에는 그 사이트 본문을 받지 않는다
"""
from __future__ import annotations

import re
import threading
from urllib.parse import urlparse

from news.core import http

# 규칙 묶음을 고를 때 쓰는 이름. User-Agent 의 제품명 부분이다.
TOKEN = http.USER_AGENT.split("/", 1)[0].lower()     # "dev-news"

MAX_BYTES = 512 * 1024      # RFC 9309 는 최소 500KiB 까지 읽으라고 한다


def parse(text: str) -> list[tuple[list[str], list[tuple[bool, str]]]]:
    """[(user-agent 목록, [(Allow 여부, 경로 규칙)])]

    User-agent 줄이 이어지면 한 묶음이고, 규칙 줄 다음에 오는 User-agent 가 새 묶음을
    연다. Sitemap·Crawl-delay 같은 다른 줄은 읽지 않는다.
    """
    groups: list[tuple[list[str], list[tuple[bool, str]]]] = []
    in_agents = False
    for raw in text.lstrip("﻿").splitlines():
        key, sep, value = raw.split("#", 1)[0].partition(":")
        if not sep:
            continue
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            if not in_agents:
                groups.append(([], []))
                in_agents = True
            groups[-1][0].append(value.lower())
        elif key in ("allow", "disallow"):
            in_agents = False
            if groups and value:            # 빈 Disallow 는 아무것도 막지 않는다
                groups[-1][1].append((key == "allow", value))
    return groups


def _matches(rule: str, path: str) -> bool:
    anchored = rule.endswith("$")
    body = rule[:-1] if anchored else rule
    regex = ".*".join(re.escape(part) for part in body.split("*"))
    return re.match(regex + (r"\Z" if anchored else ""), path) is not None


def allowed_by(text: str, url: str, token: str = TOKEN) -> bool:
    """robots.txt 본문이 이 주소를 허용하는지. 이름이 맞는 묶음이 없으면 `*` 묶음을 쓴다."""
    groups = parse(text)
    mine = ([rules for agents, rules in groups if token in agents]
            or [rules for agents, rules in groups if "*" in agents])
    parts = urlparse(url)
    path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    best: tuple[int, bool] | None = None        # (규칙 길이, Allow 여부)
    for rules in mine:
        for allow, rule in rules:
            if _matches(rule, path) and (best is None or (len(rule), allow) > best):
                best = (len(rule), allow)
    return best is None or best[1]


def _fetch(site: str) -> str | None:
    """robots.txt 본문. 파일이 없으면 "", 받지 못했으면 None."""
    try:
        # 형식은 가리지 않는다 — robots.txt 를 octet-stream 으로 주는 서버가 있다.
        resp = http.get_capped(site + "/robots.txt", timeout=10, max_bytes=MAX_BYTES,
                               allow_types=("",))
    except Exception:
        return None
    if 200 <= resp.status_code < 300:
        return resp.content.decode("utf-8", "replace")
    if 400 <= resp.status_code < 500 and resp.status_code != 429:
        return ""
    return None


class Checker:
    """사이트마다 robots.txt 를 한 번만 받는다. enrich 한 번에 하나씩 만든다.

    enrich 는 여러 스레드로 받으므로, 같은 사이트 기사가 동시에 와도 robots.txt 요청은
    한 번만 나가게 사이트별로 잠근다.
    """

    def __init__(self) -> None:
        self._rules: dict[str, str | None] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def allowed(self, url: str) -> bool:
        parts = urlparse(url)
        site = f"{parts.scheme}://{parts.netloc}"
        with self._guard:
            lock = self._locks.setdefault(site, threading.Lock())
        with lock:
            if site not in self._rules:
                self._rules[site] = _fetch(site)
        text = self._rules[site]
        return text is not None and allowed_by(text, url)
