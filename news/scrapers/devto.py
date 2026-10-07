import time
from concurrent.futures import ThreadPoolExecutor

from news.core import http
from news.core.common import published

API_URL = "https://dev.to/api/articles"
DEFAULT_TAGS = ["javascript", "python", "ai", "webdev", "typescript", "rust", "go", "devops", "security", "programming"]

# 동시 요청 수. 4개로 두었을 때 회차마다 태그 한두 개가 429로 통째로 빠졌다
# (2026-10-07 기준 최근 3주 동안 132회). 2개면 평소 직렬의 절반 시간으로 끝난다.
WORKERS = 2
# 429에 Retry-After 가 없을 때 쉬는 시간과, 있어도 넘기지 않는 상한(초).
# 상한이 없으면 서버가 1시간을 불러도 회차가 그만큼 멈춘다.
RETRY_AFTER_DEFAULT = 5
RETRY_AFTER_MAX = 30


def _retry_after(resp) -> float:
    try:
        wait = float(resp.headers.get("Retry-After", RETRY_AFTER_DEFAULT))
    except (TypeError, ValueError):
        wait = RETRY_AFTER_DEFAULT
    return min(max(wait, 0), RETRY_AFTER_MAX)


def _one(tag: str, per_tag: int) -> list[dict] | None:
    """태그 하나의 글. 요청이 실패하면 None — 글이 없는 것([])과 구분해 센다.

    429는 공용 http 가 재시도하지 않는다(상대가 쉬라는 뜻이라). 여기서는
    Retry-After 만큼 쉬고 한 번만 다시 묻는다 — 그대로 버리면 그 태그의 글이 그
    회차에서 통째로 사라진다.
    """
    params = {"tag": tag, "per_page": per_tag, "state": "rising"}
    try:
        resp = http.get(API_URL, params=params, timeout=10)
        if resp.status_code == 429:
            wait = _retry_after(resp)
            print(f"[devto] tag={tag} 429 — {wait:g}초 뒤 한 번 더")
            time.sleep(wait)
            resp = http.get(API_URL, params=params, timeout=10)
        resp.raise_for_status()
        posts = resp.json()
    except Exception as e:
        print(f"[devto] tag={tag} 오류: {e}")
        return None

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
            **published(p.get("published_at")),
        })
    return out


def fetch(tags: list[str] | None = None, per_tag: int = 10,
          counts: dict[str, int] | None = None) -> list[dict]:
    """태그를 나란히 받는다.

    직렬로 돌면 한 태그가 막힐 때 최악이 63초(재시도 3회 + 백오프)이고, 태그가
    10개라 혼자 10분을 먹는다. 워크플로 제한이 25분이라 본문 추출·요약까지
    더하면 회차가 취소될 수 있다 — 그러면 커밋이 없어 사이트가 조용히 낡는다.
    평소에는 직렬로도 6초면 끝나므로, 이건 최악의 경우를 자르는 장치다.

    동시 요청은 WORKERS 개로 묶는다. 한 사이트를 두드리는 일이라 rss(피드 10곳에
    6개)보다 절제한다.

    counts를 주면 태그별 건수를 `devto:태그`로 남긴다. 실패한 태그는 0건이다.
    합계만 세면 한 태그가 계속 429여도 devto 총계는 40건이라 아무 신호가 없다.

    태그 순서는 유지한다 — 같은 글이 여러 태그에 걸릴 때 어느 태그로 기록되는지가
    회차마다 달라지면 안 된다.
    """
    if tags is None:
        tags = DEFAULT_TAGS

    seen_urls: set[str] = set()
    articles: list[dict] = []
    failed = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for tag, got in zip(tags, pool.map(lambda t: _one(t, per_tag), tags)):
            if got is None:
                failed += 1
            if counts is not None:
                counts[f"devto:{tag}"] = len(got or [])
            for a in got or []:
                if a["url"] in seen_urls:
                    continue
                seen_urls.add(a["url"])
                articles.append(a)
    if failed:
        print(f"[devto] 태그 {len(tags)}개 중 {failed}개 실패")
    return articles
