"""무엇을 버릴지 정하는 필터들 (move-pipeline-to-core).

build.py에 있던 것을 옮겼다. 진입점이 파이프라인 로직을 들고 있어서 테스트
7개와 스크립트가 `from build import ...`로 가져다 쓰고 있었다.

깔때기 순서 (SPEC 1.2): 넓게 수집 → 여기서 걸러내고 → 점수로 선별(select.py).
파이프라인 수준의 차단 필터는 최소로 둔다 — 무엇을 보고 숨길지는 열람 단계가
담당한다 (SPEC 1.1).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from functools import lru_cache

from news.summarizer import IRRELEVANT

# 키워드 화이트리스트를 적용하지 않는 출처. 목록에 한국어가 없어서 긱뉴스
# 한국어 제목이 통과할 수 없기 때문이다 — 차단 목록은 여기에도 적용된다.
TRUSTED = {"github", "devto", "geeknews", "rss", "anthropic"}


@lru_cache(maxsize=8)
def _keyword_re(keywords: tuple[str, ...]) -> re.Pattern[str]:
    """키워드 목록을 단어경계 정규식 하나로 컴파일한다.

    부분문자열 매칭(`"ai" in "said"`)이면 필터가 통째로 무력해진다 — 실측으로
    미신뢰 출처 167건 중 166건이 통과했다. 그래서 앞뒤를 영숫자로 막는다.

    형태소는 허용하되 길이로 차등한다. 4글자 이상은 복수·시제 어미까지 받고
    (`containers`·`released`), 3글자 이하는 복수형만 받는다 — 짧은 키워드에 시제
    어미를 허용하면 `going`(go+ing)·`aid`(ai+d)가 다시 새기 때문이다.

    한글은 영숫자가 아니므로 한국어 제목은 이 경계 조건에 영향받지 않는다.
    """
    short = sorted((k for k in keywords if len(k) <= 3), key=len, reverse=True)
    long_ = sorted((k for k in keywords if len(k) > 3), key=len, reverse=True)
    parts = []
    if long_:
        parts.append("(?:" + "|".join(re.escape(k) for k in long_) + ")(?:s|es|ed|ing|d)?")
    if short:
        parts.append("(?:" + "|".join(re.escape(k) for k in short) + ")s?")
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(parts) + r")(?![a-z0-9])")


@lru_cache(maxsize=8)
def _block_re(ko: tuple[str, ...], en: tuple[str, ...]) -> re.Pattern[str] | None:
    """비개발 주제 차단 정규식.

    영어는 단어경계로 막는다 — 경계가 없으면 `war`가 `software`·`hardware`
    안에서 걸린다(실측 오탐). 한국어는 영숫자 경계가 통하지 않아 부분문자열로
    매칭되므로, `배우`(→배우다)처럼 다른 말에 파묻히는 모호어는 목록에 넣지
    않는 것으로 대응한다.
    """
    parts = []
    if ko:
        parts.append("(?:" + "|".join(re.escape(k) for k in ko) + ")")
    if en:
        parts.append(r"(?<![a-z0-9])(?:" + "|".join(re.escape(k) for k in en)
                     + r")(?![a-z0-9])")
    return re.compile("|".join(parts)) if parts else None


def keyword_filter(articles: list[dict], keywords: list[str],
                   block_keywords: dict | None = None) -> list[dict]:
    """개발 키워드로 거르고(화이트리스트), 비개발 주제를 뺀다(블랙리스트).

    화이트리스트는 TRUSTED 출처를 면제한다 — 키워드 140개에 한국어가 없어서
    긱뉴스 한국어 제목이 통과할 수 없기 때문이다. 그런데 그 면제 때문에
    비개발 기사가 그대로 실렸다(2026-08-30 배치 20건 중 4건).

    그래서 차단은 TRUSTED에도 적용한다. 면제는 "통과시킬 이유"에만 해당하지
    "빼지 않을 이유"는 아니다. 다만 차단어가 있어도 개발 키워드가 하나라도
    같이 있으면 남긴다 — `캘리포니아주 의회, 연령 확인법에서 Linux 면제`처럼
    정치 어휘를 쓰는 개발 기사를 잃지 않기 위해서다.
    """
    block_keywords = block_keywords or {}
    block = _block_re(
        tuple(k for k in (block_keywords.get("ko") or [])),
        tuple(k.lower() for k in (block_keywords.get("en") or [])),
    )
    pattern = _keyword_re(tuple(k.lower() for k in keywords)) if keywords else None

    kept, dropped, blocked = [], 0, 0
    for a in articles:
        text = (a.get("title", "") + " " + a.get("description", "")).lower()
        has_dev = bool(pattern.search(text)) if pattern else False

        if block is not None and block.search(text) and not has_dev:
            blocked += 1
            continue

        if pattern is None or a["source"] in TRUSTED or has_dev:
            kept.append(a)
        else:
            dropped += 1

    if dropped:
        print(f"[필터] 키워드 불일치 {dropped}건 제외")
    if blocked:
        print(f"[필터] 비개발 주제 {blocked}건 제외")
    return kept


def recent_only(articles: list[dict], hours: int, long_sources: dict[str, int] | None = None) -> list[dict]:
    """최근 N시간 내 발행분만 남긴다.

    long_sources에 적힌 출처는 더 긴 창을 쓴다. 공식 블로그처럼 글이 드문 곳은
    48시간으로 자르면 아예 못 보고 지나가기 때문이다. (중복은 seen.json이 막는다)
    """
    long_sources = long_sources or {}
    now = datetime.now(timezone.utc).timestamp()
    kept = []
    for a in articles:
        ts = a.get("published_at")
        if ts is None:                      # 게시 시각을 모르는 출처(GitHub 트렌딩 등)는 통과
            kept.append(a)
            continue
        window = long_sources.get(a.get("source"), hours)
        try:
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
            if float(ts) >= now - window * 3600:
                kept.append(a)
        except Exception:
            kept.append(a)
    print(f"[필터] 최근 {hours}시간 내 {len(kept)}건")
    return kept


def drop_dead_links(articles: list[dict]) -> tuple[list[dict], list[dict]]:
    """이미 사라진 링크를 게재에서 뺀다.

    판정은 enrich가 api_health.classify()로 붙여 둔 link_status를 그대로 쓴다.
    `dead`(404·410·DNS 실패·연결 거부)만 뺀다 — `unknown`(5xx·타임아웃)은
    일시 장애일 수 있고, 403·429는 봇 차단일 뿐 살아 있는 페이지다. 실측 403
    4건(economist·stanford·oup·axios)이 전부 멀쩡했다.
    """
    kept, dropped = [], []
    for a in articles:
        (dropped if a.get("link_status") == "dead" else kept).append(a)
    if dropped:
        print(f"[링크] 죽은 링크 {len(dropped)}건 게재 제외")
        for a in dropped:
            print(f"   · {a.get('url', '')[:80]}")
    return kept, dropped


def drop_irrelevant(articles: list[dict]) -> tuple[list[dict], list[dict]]:
    """LLM이 `무관`으로 분류한 기사를 게재 대상에서 뺀다.

    키워드로는 원리적으로 못 잡는 것들을 거른다 — 저작권 소송·노동 판결·학교
    성적 실험은 AI가 소재라 개발 키워드에 걸리고 차단어도 없다.

    `주변`(업계·제품 동향)은 남긴다. 경계를 좁게 잡아야 오탐으로 진짜 기사를
    잃지 않는다. 요약을 못 받은 기사(llm_done=False)는 분류도 없으므로 건드리지
    않는다 — 여기서 빼면 다음 회차 재시도 경로가 끊긴다.
    """
    kept, dropped = [], []
    for a in articles:
        if a.get("llm_done") and a.get("relevance") == IRRELEVANT:
            dropped.append(a)
        else:
            kept.append(a)
    if dropped:
        print(f"[분류] 무관 {len(dropped)}건 게재 제외")
        for a in dropped:
            print(f"   · {a.get('title', '')[:60]}")
    return kept, dropped


def page_eligible(articles: list[dict]) -> list[dict]:
    """페이지 게재 자격이 있는 것만 남긴다 (SPEC 1.1 — 기록과 게재는 별개).

    코퍼스 전용 피드(config feeds의 page: false)는 candidates 로그에는 남되
    페이지 선별 대상에서는 빠진다. 플래그가 없는 아이템은 기존대로 게재 대상.
    """
    kept = [a for a in articles if a.get("page", True)]
    excluded = len(articles) - len(kept)
    if excluded:
        print(f"[선별] 코퍼스 전용 {excluded}건 페이지 제외")
    return kept
