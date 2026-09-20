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
# 화이트리스트를 면제할 출처. 개발자들이 이미 골라 놓은 목록이라 "개발 기사인가"를
# 다시 판정할 이유가 없다. 해커뉴스·Lobsters를 여기에 넣지 않았을 때, 176개 키워드로도
# uBlock Origin·Nitter·페르마 정리 형식화 같은 기사가 계속 탈락했다 — 개발 어휘는
# 끝없이 늘어나서 목록으로 따라잡을 수 없다.
#
# 대신 차단 목록이 무거운 일을 한다. "개발 기사가 아닌 것"(연예·건강·정치·스포츠)은
# 닫힌 갈래라 목록으로 감당된다. 차단은 면제 출처에도 적용된다.
#
# ⚠️ 2026-09-15 현재 켜져 있는 출처는 전부 여기 들어 있다(trendshift는 source가
# "github"으로 기록된다). 즉 키워드 목록은 지금 한 건도 판정하지 않는다. 그래도
# 지우지 않는 이유는 둘이다 — reddit이 꺼져 있을 뿐 코드는 준비돼 있고(승인받으면
# 켜진다), 새 출처를 붙일 때 기본값이 "검사받는 쪽"이어야 안전하다.
TRUSTED = {"github", "devto", "geeknews", "rss", "anthropic", "hackernews", "lobsters"}


# 설명문에는 링크가 흔하다. 주소 문자열 안의 글자가 키워드로 잡히면 기사 주제와
# 무관하게 통과한다 — 게재된 해커뉴스·Lobsters 535건 중 44건이 그렇게 들어왔다.
# "…further discussion: https://simonwillison.net/…" 의 https가 http 키워드를,
# 주소에 든 ai·github·api가 각각 그 키워드를 대신 물어 준 것이다.
_URL_RE = re.compile(r"https?://\S+|www\.\S+")


@lru_cache(maxsize=8)
def _keyword_re(keywords: tuple[str, ...]) -> re.Pattern[str]:
    """키워드 목록을 단어경계 정규식 하나로 컴파일한다.

    부분문자열 매칭(`"ai" in "said"`)이면 필터가 통째로 무력해진다 — 실측으로
    미신뢰 출처 167건 중 166건이 통과했다. 그래서 앞뒤를 영숫자로 막는다.

    형태소는 허용하되 길이로 차등한다. 4글자 이상은 복수·시제 어미까지 받고
    (`containers`·`released`), 3글자 이하는 복수형만 받는다 — 짧은 키워드에 시제
    어미를 허용하면 `going`(go+ing)·`aid`(ai+d)가 다시 새기 때문이다.

    ⚠️ 뒤에 붙는 숫자는 막지 않는다. 막으면 `Qwen3.8`·`GPT5`·`java8`처럼 버전이
    붙은 이름이 통째로 빠진다 — 모델 발표 기사는 거의 다 이 모양이라 실제로
    DeepSeek·GLM·Qwen 발표가 전부 탈락하고 있었다. 앞은 여전히 막으므로
    `said`의 ai는 안 걸린다.

    한글은 영숫자가 아니므로 한국어 제목은 이 경계 조건에 영향받지 않는다.
    """
    short = sorted((k for k in keywords if len(k) <= 3), key=len, reverse=True)
    long_ = sorted((k for k in keywords if len(k) > 3), key=len, reverse=True)
    parts = []
    if long_:
        parts.append("(?:" + "|".join(re.escape(k) for k in long_) + ")(?:s|es|ed|ing|d)?")
    if short:
        parts.append("(?:" + "|".join(re.escape(k) for k in short) + ")s?")
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(parts) + r")(?![a-z])")


@lru_cache(maxsize=8)
def _block_re(ko: tuple[str, ...], en: tuple[str, ...]) -> re.Pattern[str] | None:
    """비개발 주제 차단 정규식.

    영어는 단어경계로 막는다 — 경계가 없으면 `war`가 `software`·`hardware`
    안에서 걸린다(실측 오탐). 한국어는 영숫자 경계가 통하지 않아 부분문자열로
    매칭되므로, `배우`(→배우다)처럼 다른 말에 파묻히는 모호어는 목록에 넣지
    않는 것으로 대응한다.

    복수형은 받는다. 목록이 전부 명사인데 `infections`가 `infection`을,
    `glp-1s`가 `glp-1`을 못 만나 그대로 통과했다. 시제 어미는 받지 않는다 —
    명사에 붙일 일이 없고 다른 말로 번질 여지만 생긴다.
    """
    parts = []
    if ko:
        parts.append("(?:" + "|".join(re.escape(k) for k in ko) + ")")
    if en:
        parts.append(r"(?<![a-z0-9])(?:" + "|".join(re.escape(k) for k in en)
                     + r")(?:e?s)?(?![a-z0-9])")
    return re.compile("|".join(parts)) if parts else None


def keyword_filter(articles: list[dict], keywords: list[str],
                   block_keywords: dict | None = None) -> list[dict]:
    """개발 키워드로 거르고(화이트리스트), 비개발 주제를 뺀다(블랙리스트).

    제목과 설명문에서 주소를 지운 뒤 본다. 주소 안 글자가 키워드로 잡히면 주제와
    무관한 기사가 통과한다.

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
        # 주소는 지우고 본다. 통과 근거도 차단 근거도 글의 주제여야 한다.
        title = _URL_RE.sub(" ", a.get("title", "").lower())
        text = _URL_RE.sub(" ", (a.get("title", "") + " "
                                 + a.get("description", "")).lower())
        has_dev = bool(pattern.search(text)) if pattern else False

        # ⚠️ 차단은 제목만 본다. 설명문까지 보면 낱말 하나가 스친 것으로 개발
        # 기사가 빠진다 — 실측으로 게재분에서 19건이 그렇게 막혔다. "딥러닝
        # 선구자 벵기오, 훈련 과정 자체가 AI를 위험하게 만든다"(설명문의 '전쟁'),
        # "미 법원, 국방부의 Anthropic 블랙리스트 지정은 위법"(설명문의 '군사')
        # 같은 것들이라 이 사이트가 놓치면 안 되는 갈래다.
        #
        # 통과 판정에는 설명문을 계속 쓴다. 제목이 짧은 기사는 그게 유일한 근거다.
        if block is not None and block.search(title) and not has_dev:
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


# '왜 중요한가'가 스스로 무관하다고 선언한 경우를 잡는 문장 형태.
# "백엔드 개발자의 업무와 무관한 영화 비하인드 스토리다" 처럼 주어가 개발자/개발이고
# 서술이 무관·관련없음인 판정문만 본다 (drop-self-declared-irrelevant). '무관' 단어만 찾으면 "유출 확인과 무관하게
# 72시간 내 통보해야 한다" 같은 조건절이 걸린다 — 실측 15건 중 8건이 그랬다.
_SELF_IRRELEVANT = re.compile(
    r"(백엔드|개발자|AI 개발|개발)[^.]{0,40}?(업무|실무|현장|아키텍처)?[^.]{0,25}?"
    r"(와|과)\s*(직접적인\s*)?(무관|관련이?\s*없)"
)


def drop_self_declared_irrelevant(articles: list[dict]) -> tuple[list[dict], list[dict]]:
    """'개발자의 업무와 무관하다'고 요약이 스스로 말한 기사를 게재에서 뺀다.

    프롬프트는 그런 판정을 쓰지 말라고 금지한다(summarizer.PROMPT). 금지를 어기고
    나왔다면 모델이 이 기사에서 개발자용 의미를 찾다 실패한 것이다.

    LLM 분류 게이트와 다른 신호다. 최근 10일 540건에서 9건이 걸렸고 오탐은 없었다.
    그 9건 중 5건은 분류가 `게재`로 통과시킨 것들이었다 — 분류가 놓치는 자리를 메운다.
    추가 호출이 없으므로 relevance_gate와 무관하게 켤 수 있다.
    """
    kept, dropped = [], []
    for a in articles:
        why = re.sub(r"\s+", " ", a.get("why") or "")
        (dropped if why and _SELF_IRRELEVANT.search(why) else kept).append(a)
    if dropped:
        print(f"[요약자평] 무관 선언 {len(dropped)}건 게재 제외")
        for a in dropped:
            print(f"   · {(a.get('ko_title') or a.get('title', ''))[:60]}")
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
