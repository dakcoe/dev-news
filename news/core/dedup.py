"""중복 기사 판정 — URL 정규화 1단, 제목 유사도 2단.

기존에는 URL 완전일치(build.dedupe)와 정규화 제목 앞 60자 완전일치(scorer)를
따로 썼다. 둘 다 완전일치라 같은 사건을 여러 소스가 물어오면 만나지 않았고,
2026-08-30 배치에 캘리포니아 Linux 면제 기사가 두 건으로 나란히 실렸다.

한국어 제목은 토큰이 겹치지 않아 2단으로 잡을 수 없다. 그쪽은 긱뉴스가 원문
URL을 들고 오게 만들어 1단에서 걸리게 한다 (scrapers/geeknews.py).

중복은 버리지 않고 합친다 — 여러 소스가 동시에 다룬 글은 실제로 더 중요하다는
기존 설계(scorer.py의 cross_source_count * 300)를 살린다.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# 광고·유입 추적용이라 같은 글이어도 값이 달라진다. 지우지 않으면 1단이 무력해진다.
TRACKING_PREFIXES = ("utm_", "ref_")
TRACKING_KEYS = {
    "ref", "source", "src", "fbclid", "gclid", "mc_cid", "mc_eid",
    "igshid", "spm", "at_medium", "at_campaign", "s",
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_HANGUL_RE = re.compile(r"[가-힣]+")

# 버전·릴리스 번호. 이게 다르면 같은 글일 수 없다 — 실측에서 sqlite-utils 4.2.1과
# 4.2가 0.8, llm-anthropic 0.27과 0.26이 0.6으로 합쳐질 뻔했다.
_VERSION_RE = re.compile(r"^v?\d+(?:\.\d+)+[a-z]*\d*$|^\d+\.\d+$")

# owner / repo 형태. 이름이 다르면 다른 저장소다
# (anthropics/claude-plugins-official 과 -community 가 0.6이었다).
_OWNER_REPO_RE = re.compile(r"^\s*([\w.+-]+)\s*/\s*([\w.+-]+)\s*$")

# 토큰이 이보다 적으면 유사도 판정을 포기한다(0.0을 돌려준다).
# 한국어 제목은 영숫자 토큰이 한두 개뿐이라 {'debian'} vs {'debian'} 같은
# 한 토큰짜리 교집합이 1.0으로 나온다 — 서로 다른 기사가 합쳐진다.
MIN_TOKENS = 4

# 제목 유사도가 이 값 이상이면 같은 글로 본다. 실측 쌍에서 동일 기사는 0.5~1.0,
# 무관한 쌍은 0.2 아래였다.
SIMILARITY_THRESHOLD = 0.6

# 자카드 분모를 키우기만 하는 흔한 기능어. 빼야 같은 글의 표현 차이를 넘는다.
STOPWORDS = {
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is", "are",
    "it", "its", "with", "that", "this", "as", "at", "by", "from", "be", "was",
    "you", "your", "we", "our", "not", "but", "can", "has", "have",
    # 사이트 접두사 — 글 내용과 무관한데 겹침만 키운다 (Show GN 글끼리 0.6이었다)
    "show", "gn", "hn", "ask", "tell",
}

# 한국어 조사·어미. 앞 단어에서 떨어져 나와 토큰이 된다("Sol은" → sol + 은).
HANGUL_STOPWORDS = {
    "은", "는", "이", "가", "을", "를", "의", "에", "와", "과", "로", "으로",
    "도", "만", "에서", "에게", "한", "하는", "된", "되는", "및", "수", "것",
}


def normalize_url(url) -> str:
    """비교용 URL 키. 스킴·www·추적 파라미터·프래그먼트·말미 슬래시를 지운다.

    형식이 깨진 값이 들어와도 예외를 던지지 않는다 — 수집물에는 별별 것이 다 온다.
    """
    if not url or not isinstance(url, str):
        return ""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip().lower()

    host = (parts.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]

    # 의미 있는 파라미터는 남긴다 — 긱뉴스 토픽은 ?id= 로만 구분된다
    query = urlencode(sorted(
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not (k.lower().startswith(TRACKING_PREFIXES) or k.lower() in TRACKING_KEYS)
    ))

    path = (parts.path or "").rstrip("/")
    if not host and not path:
        return url.strip().lower()
    return urlunsplit(("", host, path, query, "")).lstrip("/").lower() or url.strip().lower()


def _tokens(title: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall((title or "").lower()) if t not in STOPWORDS}


def _hangul_tokens(title: str) -> set[str]:
    return {t for t in _HANGUL_RE.findall(title or "") if t not in HANGUL_STOPWORDS}


def _versions(title: str) -> set[str]:
    return {t for t in re.findall(r"[\w.+-]+", (title or "").lower())
            if _VERSION_RE.match(t)}


def _blocked(a: str, b: str) -> bool:
    """같은 글일 수 없는 조합을 먼저 걸러낸다."""
    va, vb = _versions(a), _versions(b)
    if va and vb and va != vb:
        return True

    ma, mb = _OWNER_REPO_RE.match(a or ""), _OWNER_REPO_RE.match(b or "")
    if ma and mb and (ma.group(1).lower(), ma.group(2).lower()) !=                      (mb.group(1).lower(), mb.group(2).lower()):
        return True

    # 둘 다 한국어 제목이면 한국어 쪽도 겹쳐야 한다. 한국어 제목은 영숫자 토큰이
    # 제품명 조각만 남아서, 같은 제품에 대한 서로 다른 글이 전부 비슷해 보인다
    # ("GPT-5.6 Sol 가격 50% 인하" ⇄ "GPT-5.6 Sol은 최고의 비전 모델"이 0.67).
    # 한쪽만 한국어인 교차언어 쌍에는 적용하지 않는다 — 그건 잡아야 하는 쌍이다.
    ha, hb = _hangul_tokens(a), _hangul_tokens(b)
    if len(ha) >= 2 and len(hb) >= 2:
        overlap = len(ha & hb) / len(ha | hb)
        if overlap < 0.3:
            return True
    return False


def title_similarity(a: str, b: str) -> float:
    """두 제목의 자카드 유사도. 토큰이 너무 적으면 판정을 포기하고 0.0."""
    if _blocked(a, b):
        return 0.0
    ta, tb = _tokens(a), _tokens(b)
    if len(ta) < MIN_TOKENS or len(tb) < MIN_TOKENS:
        return 0.0
    union = ta | tb
    if not union:
        return 0.0
    return len(ta & tb) / len(union)


def _score(a: dict) -> float:
    try:
        return float(a.get("score") or 0)
    except (TypeError, ValueError):
        return 0.0


def merge_duplicates(articles: list[dict]) -> list[dict]:
    """중복을 합쳐 대표 1건만 남긴다.

    대표는 점수가 높은 쪽. 합쳐진 항목에는 merged_sources(출처 이름 집합)와
    cross_source_count(서로 다른 출처 수)를 채워 scorer의 가산에 쓰이게 한다.
    """
    if not articles:
        return []

    groups: list[dict] = []          # {"url_keys": set, "titles": list, "items": list}
    by_url: dict[str, int] = {}

    for a in articles:
        key = normalize_url(a.get("url"))
        idx = by_url.get(key) if key else None

        if idx is None:
            for i, g in enumerate(groups):
                if any(title_similarity(a.get("title", ""), t) >= SIMILARITY_THRESHOLD
                       for t in g["titles"]):
                    idx = i
                    break

        if idx is None:
            groups.append({"titles": [a.get("title", "")], "items": [a]})
            idx = len(groups) - 1
        else:
            groups[idx]["titles"].append(a.get("title", ""))
            groups[idx]["items"].append(a)

        if key:
            by_url.setdefault(key, idx)

    out = []
    for g in groups:
        items = g["items"]
        best = max(items, key=_score)
        # 출처는 feed까지 구분해 센다 — Trendshift는 source=github이지만 별개 신호다
        # (add-trendshift-source). rss 피드 두 곳이 같은 글을 물어와도 마찬가지.
        sources = sorted({i.get("feed") or i.get("source") for i in items
                          if i.get("source")})
        merged = {**best, "merged_sources": sources,
                  "cross_source_count": max(len(sources), 1)}
        out.append(merged)

    dropped = len(articles) - len(out)
    if dropped:
        print(f"[중복] {dropped}건 병합")
    return out
