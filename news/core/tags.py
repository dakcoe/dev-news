"""닫힌 어휘 태거 (SPEC 1B — add-article-tags).

179건 코퍼스 분석으로 도출한 범용 카테고리 어휘. LLM 자유 태그 생성 금지 —
어휘는 여기 VOCAB에 고정되고, 규칙(키워드 패턴) 매칭으로만 부여한다.
결정적이므로 어휘를 고치면 소급 재태깅이 공짜다 (scripts/retag.py).

패턴은 소문자화된 "제목 + ko_title + 설명 + 요약" 텍스트에 대한 정규식.
한글은 조사가 붙으므로 \\b 없이 부분 일치, 짧은 영문 토큰은 \\b로 경계를 준다.
"""
from __future__ import annotations

import re

# 태그 어휘 — 순서가 우선순위다 (MAX_TAGS 초과 시 뒤쪽부터 버린다).
VOCAB: dict[str, dict] = {
    "ai": {
        "label": "AI",
        "group": "AI",
        "patterns": [r"\bai\b", r"인공지능", r"machine learning", r"머신러닝",
                     r"deep learning", r"딥러닝", r"\bneural", r"openai",
                     r"anthropic", r"deepmind", r"\bxai\b", r"허깅\s?페이스",
                     r"hugging face"],
    },
    "llm": {
        "label": "LLM · 모델",
        "group": "AI",
        "patterns": [r"\bllms?\b", r"\bgpt", r"claude", r"gemini", r"qwen",
                     r"deepseek", r"\bllama", r"mistral", r"chatgpt", r"grok",
                     r"언어\s?모델", r"transformer", r"\binference\b", r"추론",
                     r"프롬프트", r"prompt", r"\btokens?\b", r"토큰",
                     r"open[- ]?weights?", r"reasoning", r"\brag\b",
                     r"\bfable\b", r"\bmythos\b", r"\bopus\b"],
    },
    "ai-agent": {
        "label": "에이전트",
        "group": "AI",
        "patterns": [r"\bagents?\b", r"agentic", r"에이전트", r"\bmcp\b",
                     r"autogpt", r"multi[- ]agent", r"harness", r"하네스",
                     r"\bskills?\b", r"스킬"],
    },
    "ai-coding": {
        "label": "AI 코딩",
        "group": "AI",
        "patterns": [r"claude\s?code", r"copilot", r"cursor", r"codex",
                     r"vibe\s?coding", r"바이브\s?코딩", r"ai[- ]?(assisted\s)?cod(ing|e)",
                     r"coding\s(agent|assistant|cli)", r"코딩\s(에이전트|보조)",
                     r"ai\s?(생성|작성)\s?코드", r"ai[- ]generated\scode", r"muse\s?code"],
    },
    "gen-media": {
        "label": "생성 미디어",
        "group": "AI",
        "patterns": [r"image\s?gen", r"text-to-image", r"diffusion", r"\bsuno\b",
                     r"\bflux\b", r"seedance", r"midjourney", r"이미지\s?생성",
                     r"영상\s?생성", r"video\s?(gen|model)", r"ai\s?music",
                     r"music\s?generat", r"gpt-image", r"imagine\s?image", r"\bsora\b"],
    },
    "ai-safety": {
        "label": "AI 안전 · 정책",
        "group": "AI",
        "patterns": [r"safety", r"안전", r"alignment", r"정렬\s?문제", r"guardrail",
                     r"가드레일", r"jailbreak", r"safeguard", r"misuse", r"오남용",
                     r"red[- ]team", r"\brogue\b", r"unsanctioned", r"cheating",
                     r"부정행위", r"restricts?\b", r"규제", r"sycophan", r"blast radius",
                     r"\baisi\b"],
    },
    "research": {
        "label": "연구 · 벤치마크",
        "group": "그 외",
        "patterns": [r"\bpaper\b", r"arxiv", r"research", r"\bstudy\b", r"benchmark",
                     r"논문", r"연구", r"벤치마크", r"arc-agi", r"\bevals?\b",
                     r"평가", r"\bsota\b", r"retrieval", r"entropy", r"markov"],
    },
    "security": {
        "label": "보안",
        "group": "개발",
        "patterns": [r"secur", r"보안", r"vulnerab", r"취약점", r"\bcve\b",
                     r"phish", r"피싱", r"backdoor", r"백도어", r"exploit",
                     r"malware", r"encrypt", r"암호화", r"osint", r"hack(ed|ing|er)",
                     r"해킹", r"passkey", r"password", r"비밀번호", r"\bauth\w*",
                     r"social engineering", r"사회공학", r"cyber", r"사이버", r"privacy",
                     r"프라이버시", r"침해"],
    },
    "dev-tools": {
        "label": "개발 도구",
        "group": "개발",
        "patterns": [r"\bcli\b", r"terminal", r"터미널", r"\beditor\b", r"\bide\b",
                     r"\bgit\b", r"debugg", r"디버거", r"디버깅", r"jujutsu",
                     r"\btool(s|ing)?\b", r"도구", r"workflow", r"productivity",
                     r"생산성", r"\bsdk\b", r"dotfiles"],
    },
    "web": {
        "label": "웹 · 프론트엔드",
        "group": "개발",
        "patterns": [r"browser", r"브라우저", r"javascript", r"typescript",
                     r"\bcss\b", r"\breact\b", r"angular", r"\bvue\b", r"next\.?js",
                     r"frontend", r"프론트엔드", r"\bweb\b", r"웹", r"html",
                     r"\bsvg\b", r"\bdom\b", r"tailwind", r"wasm", r"chrome",
                     r"firefox", r"ladybird"],
    },
    "backend-data": {
        "label": "백엔드 · 데이터",
        "group": "개발",
        "patterns": [r"database", r"데이터베이스", r"postgres", r"\bsql\b", r"redis",
                     r"\bapi\b", r"backend", r"백엔드", r"\bserver\b", r"서버",
                     r"sqlite", r"datasette", r"크롤링", r"scrap(ing|er)", r"crawl",
                     r"\bdns\b", r"analytics", r"파이프라인", r"pipeline"],
    },
    "devops-infra": {
        "label": "인프라 · 클라우드",
        "group": "개발",
        "patterns": [r"kubernetes", r"\bk8s\b", r"docker", r"container", r"ci/cd",
                     r"github actions", r"deploy", r"배포", r"\bcloud\b", r"클라우드",
                     r"\baws\b", r"infra", r"인프라", r"datacenter", r"데이터센터",
                     r"self[- ]?host", r"셀프호스팅", r"serverless", r"\bcompute\b",
                     r"cloudflare", r"vercel", r"가용성", r"availability", r"outage"],
    },
    "hardware": {
        "label": "하드웨어 · 칩",
        "group": "그 외",
        "patterns": [r"\bcpu\b", r"\bgpu\b", r"\bchips?\b", r"칩\b", r"silicon",
                     r"실리콘", r"nvidia", r"\bamd\b", r"intel", r"\barm\b",
                     r"semiconductor", r"반도체", r"\bmemory\b", r"메모리",
                     r"firmware", r"펌웨어", r"esp32", r"x86", r"risc-v",
                     r"하드웨어", r"\bcuda\b", r"rocm", r"\btpu\b", r"\bphone\b",
                     r"스마트폰", r"smartphone"],
    },
    "language": {
        "label": "언어 · 런타임",
        "group": "개발",
        "patterns": [r"\brust\b", r"러스트", r"python", r"파이썬", r"golang",
                     r"\bjava\b", r"자바\b", r"kotlin", r"swift", r"c\+\+",
                     r"assembly", r"어셈블리", r"compiler", r"컴파일러", r"runtime",
                     r"런타임", r"prolog", r"\bzig\b", r"openjdk", r"\bnode\.?js\b",
                     r"\bdeno\b", r"\bv8\b"],
    },
    "open-source": {
        "label": "오픈소스",
        "group": "그 외",
        "patterns": [r"open[- ]?sourc", r"오픈소스", r"\boss\b", r"licen[cs]e",
                     r"라이선스", r"maintainer", r"유지보수", r"contributor", r"기여"],
    },
    "release": {
        "label": "릴리스 · 출시",
        "group": "그 외",
        "patterns": [r"releas", r"릴리스", r"출시", r"\blaunch", r"introducing",
                     r"announc", r"발표", r"공개", r"generally available",
                     r"now available", r"\bv?\d+\.\d+\.\d+\b", r"인수", r"acquir",
                     r"업데이트", r"\bupdate"],
    },
    "industry": {
        "label": "업계 · 비즈니스",
        "group": "그 외",
        "patterns": [r"acquir", r"인수", r"\bceo\b", r"funding", r"\bipo\b",
                     r"market", r"시장", r"revenue", r"매출", r"layoff", r"해고",
                     r"startup", r"스타트업", r"y combinator", r"partner", r"파트너",
                     r"퇴사", r"사임", r"steps? down", r"billion", r"\$\d", r"주가",
                     r"매진", r"invest", r"enterprise", r"기업", r"고객", r"경쟁",
                     r"app\s?store", r"앱스토어"],
    },
    "career-culture": {
        "label": "커리어 · 문화",
        "group": "그 외",
        "patterns": [r"career", r"커리어", r"경력", r"\bjobs?\b", r"직군",
                     r"community", r"커뮤니티", r"culture", r"문화", r"programmer",
                     r"프로그래머", r"\bhobby\b", r"취미", r"interview", r"인터뷰",
                     r"\bcourse\b", r"강의", r"humor", r"유머", r"essay", r"에세이",
                     r"opinion", r"채용", r"hiring", r"모욕", r"교육", r"student",
                     r"학생", r"(software|tech)\s?talks", r"강연", r"\bquoting\b"],
    },
    "science": {
        "label": "과학 · 우주",
        "group": "그 외",
        "patterns": [r"\bspace\b", r"우주", r"\bnasa\b", r"physics", r"물리",
                     r"\bmath\b", r"수학", r"astronom", r"galax", r"은하",
                     r"observatory", r"voyager", r"eclipse", r"일식", r"weather",
                     r"날씨", r"사이클론", r"cyclone", r"biolog", r"생물", r"quantum",
                     r"양자", r"telescope", r"위성", r"satellite", r"항공"],
    },
    "showcase": {
        "label": "쇼케이스",
        "group": "그 외",
        "patterns": [r"show\s?gn", r"show\s?hn", r"i built", r"i made",
                     r"만들었", r"직접 만든", r"사이드\s?프로젝트", r"side project"],
    },
}

# 세부 태그 → 상위 태그 자동 부여 (평균 3~4개의 한 축)
IMPLIES: dict[str, str] = {
    "llm": "ai",
    "ai-agent": "ai",
    "ai-coding": "ai",
    "gen-media": "ai",
    "ai-safety": "ai",
}

# 패턴 없이 암시로만 부여되는 태그 (현재 없음 — test_vocab_integrity가 참조)
IMPLIED_ONLY: set[str] = set()

# 출처 자체가 의미를 갖는 경우 (GitHub 트렌딩 = 오픈소스 저장소)
SOURCE_IMPLIES: dict[str, str] = {
    "github": "open-source",
}

# 제목에서만 인정하는 "약한" 패턴.
#
# 태거는 제목+ko_title+설명+요약 전부를 훑는데, 요약은 LLM이 쓴 부연이라 본문
# 주제와 먼 단어가 흔하다. 범용 한국어 명사가 스치듯 등장해 태그가 됐다 —
# 단독으로 태그를 만든 패턴을 1,272건에서 세어 보니 상위가 전부 이런 말이었다
# (공개 114 · 도구 136 · 연구 68 · 서버 53 · 기업 33 · 커뮤니티 33).
#
#   "은하 상태를 보관하고"(게임 세계관) → science
#   "HTML 형식의 문서를 지원"           → web
#
# 고유명사·전문용어(openai, claude, css, kubernetes)는 어디서 나와도 그 기사의
# 소재이므로 약하게 두지 않는다. 요약을 통째로 빼는 안은 폐기했다 — 실측에서
# 123건이 태그 0개가 되고 정당한 llm 태그 140건이 사라졌다.
WEAK_PATTERNS = {
    r"공개", r"발표", r"업데이트", r"출시", r"인수",
    r"도구", r"연구", r"평가", r"서버", r"웹", r"배포", r"안전", r"보안",
    r"기업", r"고객", r"경쟁", r"시장", r"커뮤니티", r"문화", r"교육",
    r"성능", r"최적화", r"테스트", r"오류", r"버그",
    r"programmer", r"프로그래머", r"interview", r"인터뷰", r"opinion",
    r"\btool(s|ing)?\b", r"\bstudy\b", r"market", r"community", r"culture",
    r"은하", r"galax", r"물리", r"수학", r"위성", r"항공", r"날씨",
    r"해킹", r"html",
}

MAX_TAGS = 4

_COMPILED = {tid: [re.compile(p) for p in spec["patterns"]
                   if p not in WEAK_PATTERNS]
             for tid, spec in VOCAB.items()}

# 약한 패턴은 제목에만 적용한다
_COMPILED_WEAK = {tid: [re.compile(p) for p in spec["patterns"]
                        if p in WEAK_PATTERNS]
                  for tid, spec in VOCAB.items()}


_HANGUL_BOUNDARY = re.compile(r"(?<=[a-zA-Z0-9])(?=[가-힣])|(?<=[가-힣])(?=[a-zA-Z0-9])")


def _normalize(*parts) -> str:
    text = " ".join(p or "" for p in parts).lower()
    # "DNS에서"처럼 영단어에 조사가 붙으면 \b 경계가 안 잡힌다(한글도 \w) — 사이를 띄운다
    return _HANGUL_BOUNDARY.sub(" ", text)


def _text_of(article: dict) -> str:
    return _normalize(article.get("title"), article.get("ko_title"),
                      article.get("description"), article.get("summary"))


def _title_of(article: dict) -> str:
    """약한 패턴을 검사할 범위 — 출처가 준 원제목만.

    ko_title과 summary는 LLM이 만든 글이라 원문에 없는 말이 섞인다. 실제로
    "Aspect-Ratio Hack"이 "비율 해킹"으로 오역돼 CSS 기사에 security 태그가
    붙었고, 요약의 "HTML 형식의 문서"가 web 태그를 만들었다. 원제목에 있으면
    그 기사의 주제이므로 인정한다.
    """
    return _normalize(article.get("title"))


def tag_article(article: dict) -> list[str]:
    """닫힌 어휘에서 매칭되는 태그를 우선순위(VOCAB 순서)대로 반환. 최대 MAX_TAGS개."""
    text = _text_of(article)
    title = _title_of(article)
    got: list[str] = [tid for tid in VOCAB
                      if any(p.search(text) for p in _COMPILED[tid])
                      or any(p.search(title) for p in _COMPILED_WEAK[tid])]

    src_tag = SOURCE_IMPLIES.get(article.get("source", ""))
    if src_tag and src_tag not in got:
        got.append(src_tag)
    for tid in list(got):
        implied = IMPLIES.get(tid)
        if implied and implied not in got:
            got.append(implied)

    # 어휘 순서로 정렬해 출력 순서를 안정화하고 상한을 적용
    order = {tid: i for i, tid in enumerate(VOCAB)}
    got.sort(key=lambda t: order[t])
    return got[:MAX_TAGS]


def tag_all(articles: list[dict]) -> list[dict]:
    """기사 목록에 tags 필드를 채워 넣는다 (제자리 수정 + 반환)."""
    for a in articles:
        a["tags"] = tag_article(a)
    return articles


def label(tag_id: str) -> str:
    return VOCAB.get(tag_id, {}).get("label", tag_id)
