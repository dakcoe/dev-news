"""제목 번역 · 새 정보 중심 요약 · '왜 중요한가' 생성 (SPEC 1.3 · 1.6).

공급자는 Groq 전용 (무료). LLM_PROVIDER 추상화는 하위 호환으로만 남긴다 —
새 공급자를 추가하지 말 것.

한도 대응 (SPEC 1.6):
  - 429는 Retry-After를 존중해 최대 2회만 재시도. 그래도 실패하면 서킷 브레이커가
    열리고 이번 실행의 나머지 LLM 호출은 시도조차 하지 않는다.
  - 기사는 선별 랭킹 순서대로 처리 — 한도에 걸리면 하위 기사부터 요약이 빠진다.
  - 요약을 못 받은 기사는 llm_done=False로 반환된다. 빌드는 이런 기사를
    게시하지 않고 seen에도 넣지 않는다 (다음 실행에서 재탐지).
  - max_calls로 실행당 호출 예산을 건다 (config llm.max_calls_per_run).
"""
from __future__ import annotations

import os
import re
import time

import requests

PROVIDER = os.environ.get("LLM_PROVIDER", "groq").lower()

DEFAULT_MODELS = {
    # A/B 실측(동일 기사 10건)으로 llama-3.3-70b에서 교체 — switch-summarizer-model.
    # 결정적 차이는 번역 정확도였다. "…Medical Research Is 100% AI"(폭로 기사)를
    # llama는 "의학 연구를 위한 논문 초안 제공"으로 옮겨 핵심을 통째로 날렸다.
    # methodologist를 "메소도론가"로 오역하고 "있음을모르다하다" 같은 비문도 냈다.
    "groq": "openai/gpt-oss-120b",
    "openrouter": "meta-llama/llama-3.3-70b-instruct:free",
    "gemini": "gemini-3.1-flash-lite",
}

ENDPOINTS = {
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
}

KEY_ENV = {
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "gemini": "GEMINI_API_KEY",
}

SYSTEM = ("너는 한국인 개발자를 위한 기술 뉴스 브리핑 편집자다. 지시한 형식만 출력하고 다른 말은 절대 붙이지 않는다. "
          "출력에는 한글·영문·숫자·문장부호만 쓴다. 그 외 문자(중국어 한자·일본어 가나·키릴·태국 문자 등)를 절대 쓰지 마라 — 한자어는 반드시 한글로 적는다 (예: 离任(X)→물러남(O), 超越(X)→뛰어넘기(O)).")

# Llama 계열은 한국어 생성 중 한자뿐 아니라 가나·키릴·태국 문자 등 다국어 토큰을
# 섞어 출력하는 버릇이 있다 (실측: 테็กซ스, 프로토タイプ, нос고). 스크립트를 나열해
# 막는 블랙리스트는 새는 스크립트가 생길 때마다 뚫리므로, SYSTEM이 선언한 허용
# 집합(한글·영문·숫자·문장부호)의 화이트리스트로 검사한다.
# 프롬프트 금지만으로는 가끔 새므로: 감지 시 재생성 1회 → 그래도 남으면
# 해당 단어만 추출해 번역·일괄 치환 → 그래도 남으면 미게시.
FOREIGN_RE = re.compile(
    r"[^ -~"                # ASCII (영문·숫자·문장부호·공백)
    r"가-힣ㄱ-ㅣ"  # 한글 음절 · 호환 자모
    r"£¥°±·×"      # £ ¥ ° ± · ×
    r"‐-―‘’“”…"  # 하이픈·대시류, 따옴표, 말줄임
    r"←→↔"          # 화살표 — "SVG→PDF"처럼 쓸모가 있다
    r"₩€]"               # ₩ €
)

# 모델이 섞어 쓰는 무해한 공백·기호를 ASCII로 정규화한다. 외국 문자 검사보다
# 먼저 돌려야 오탐으로 재생성·미게시되는 낭비가 없다 — gpt-oss 실측에서 걸린 건
# 한자·가나가 아니라 U+202F(좁은 비분리 공백) 12건과 → 1건뿐이었다.
# 저장물도 같이 깨끗해진다 (JSON에 보이지 않는 공백이 남지 않는다).
SYMBOL_MAP = {
    0x00A0: " ", 0x2007: " ", 0x2009: " ", 0x202F: " ",   # 각종 비분리·얇은 공백
    0x2060: "", 0xFEFF: "",                                 # 폭 없는 결합자·BOM
    0x2011: "-",                                            # 비분리 하이픈
}


def _normalize_symbols(text: str) -> str:
    return text.translate(SYMBOL_MAP)
FOREIGN_RUN_RE = re.compile(FOREIGN_RE.pattern + "+")   # 연속 런 (단어 단위 추출용)

FOREIGN_FIX_PROMPT = """아래 한국어 문장에 외국 문자(한자·가나·키릴 등)가 잘못 섞여 있다. 나열된 단어를 한국어로 옮겨라.
한자는 가능하면 한국 한자음 독음으로 옮겨라 (예: 超越=초월, 离任=이임, 金融=금융) — 문장의 조사·어미와 자연스럽게 이어지도록. 독음이 한국어에서 안 쓰이는 단어일 때만 뜻으로 번역해라.
그 외 문자는 문맥에 맞는 한국어 표기로 옮겨라 (예: タイプ=타입, прогресс=진전).
각 줄에 "원문=한국어" 형식으로만 출력하고 다른 말은 절대 붙이지 마라.

[문맥]
{context}

[번역할 단어]
{words}
"""

# 요약 원칙 (SPEC 1.3): 제목 복창 금지. 제목에 없는 새 정보만.
# 독자는 한 명으로 고정 — 백엔드·AI를 다루는 개발자가 자기 일에 쓸지 판단할 수 있게.
PROMPT = """아래 기사를 다음 형식으로만 출력해라.

번역제목: (반드시 한국어가 포함돼야 한다. 이미 한국어면 그대로 두고, 외국어 문장이면 자연스러운 한국어로 옮겨라. 저장소명·패키지명·제품명·버전처럼 옮길 수 없는 고유명사가 제목의 전부라면 번역하지 말고 뒤에 설명을 붙여라 — "원래이름 — 한 줄 한국어 설명" 형태. 예: "datasette-upload-dbs 0.5a0 — Datasette에 SQLite DB를 올리는 플러그인", "owner / repo — 한 줄 설명". 원제를 영어 그대로 복사하는 것은 금지다)
요약: (2~4문장. 제목에 이미 있는 정보를 반복하지 마라. 제목에 없는 새 정보만 써라 — 구체적으로 무엇이 새로운지, 왜 지금 주목받는지, GitHub 저장소라면 기술 스택과 쓰임새. 독자는 백엔드·AI를 다루는 개발자 한 명이고, 자기 일에 쓸지 판단하는 데 필요한 것만. 원문에 없는 내용은 절대 지어내지 마라. 제목 외에 덧붙일 정보가 본문에 없으면 "없음"이라고만 써라)
왜중요: (한 문장. 그 개발자의 일에 어떤 의미인지. 덧붙일 것이 없으면 "없음")

[기사]
제목: {title}
출처: {source}
본문: {body}
"""

LABELS = {"번역제목": "ko_title", "요약": "summary", "왜중요": "why"}


def _clean(line: str) -> str:
    line = re.sub(r"^#+\s*", "", _normalize_symbols(line).strip())
    return line.replace("**", "").replace("*", "")


# PROMPT가 "덧붙일 정보가 없으면 '없음'"이라 지시하는데, 모델이 정상 요약 뒤에
# "… 계획이다. 없음"이나 "기술 스택 정보는 없음."처럼 답을 덧붙이는 누출이 있다.
# 정상 한국어 문어체 문장은 "없음"으로 끝나지 않으므로(없다/없었다로 끝남),
# "없음"으로 끝나는 마지막 문장은 템플릿 반응으로 보고 제거한다.
_NO_INFO_TAIL_RE = re.compile(r"(?:(?<=[.!?])|^)\s*[^.!?]*없음[.!?]?\s*$")


def _strip_no_info_tail(text: str) -> str:
    while True:
        stripped = _NO_INFO_TAIL_RE.sub("", text).rstrip()
        if stripped == text:
            return text
        text = stripped


def _parse(text: str) -> dict:
    buf: dict[str, list[str]] = {"ko_title": [], "summary": [], "why": []}
    section = None
    for raw in text.splitlines():
        line = _clean(raw)
        hit = False
        for label, key in LABELS.items():
            if line.startswith(label + ":") or line.startswith(label + " :"):
                section = key
                value = line.split(":", 1)[1].strip()
                if value:
                    buf[key].append(value)
                hit = True
                break
        if not hit and section and line:
            buf[section].append(line)
    out = {k: " ".join(v).strip() for k, v in buf.items()}
    # "없음" = 덧붙일 정보가 없다는 답 → 빈 문자열 (UI가 요약 줄을 생략한다)
    for k in ("summary", "why"):
        text = _strip_no_info_tail(out[k] or "")
        if re.fullmatch(r"[\s\"'()\[\]]*없음[\s.\"'()\[\]]*", text):
            text = ""
        out[k] = text
    return {k: (v or None) if k == "ko_title" else v for k, v in out.items()}


# ---------------------------------------------------------------- providers
class RateLimited(Exception):
    """429. 서버가 알려준 대기 시간을 담는다."""

    def __init__(self, wait: float):
        super().__init__(f"rate limit (429) — {wait:.0f}초 대기")
        self.wait = wait


def _retry_after(resp: requests.Response) -> float:
    """Retry-After 헤더를 초 단위로. 없으면 60초."""
    raw = resp.headers.get("retry-after") or resp.headers.get("x-ratelimit-reset-tokens", "")
    m = re.match(r"^\s*([\d.]+)\s*(ms|m|s)?\s*$", str(raw))
    if m:
        value, unit = float(m.group(1)), (m.group(2) or "s")
        return {"ms": value / 1000, "s": value, "m": value * 60}[unit]
    return 60.0


def _call_openai_compatible(prompt: str, model: str, api_key: str, url: str) -> str:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 800,
    }
    # gpt-oss는 추론형이라 추론 토큰도 max_tokens를 먹는다. 기본값(medium)이면
    # 추론이 예산을 다 써서 content가 빈 문자열로 온다 — 실측 10건 중 2건.
    # low로 낮추면 10/10 정상. 요약은 긴 추론이 필요한 작업이 아니다.
    if "gpt-oss" in model:
        payload["reasoning_effort"] = "low"
    resp = requests.post(url, headers=headers, json=payload, timeout=90)
    if resp.status_code == 429:
        raise RateLimited(_retry_after(resp))
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    # 추론형 모델은 content가 없고 reasoning만 오는 경우가 있다 — None이 아니라
    # 빈 문자열로 넘겨서 호출자의 파싱 실패 재시도 경로를 타게 한다.
    return resp.json()["choices"][0]["message"].get("content") or ""


def _call_gemini(prompt: str, model: str, api_key: str) -> str:
    from google import genai  # 이 공급자를 쓸 때만 필요
    client = genai.Client(api_key=api_key)
    resp = client.models.generate_content(model=model, contents=SYSTEM + "\n\n" + prompt)
    return resp.text or ""


def _call(prompt: str, provider: str, model: str, api_key: str) -> str:
    if provider == "gemini":
        return _call_gemini(prompt, model, api_key)
    return _call_openai_compatible(prompt, model, api_key, ENDPOINTS[provider])


def _translate_foreign(parsed: dict, provider: str, model: str, api_key: str) -> dict | None:
    """잔존 외국 문자를 추출·번역해 일괄 치환한다. 실패하면 None (호출자는 미게시 처리).

    같은 단어가 여러 번 나와도 매핑 하나로 모두 치환된다. 매핑이 불완전하거나
    번역값에 또 외국 문자가 있으면 포기하고, 치환 후에도 전체를 재검증한다.
    """
    joined = " ".join(filter(None, [parsed.get("ko_title"), parsed.get("summary"),
                                    parsed.get("why")]))
    words = list(dict.fromkeys(FOREIGN_RUN_RE.findall(joined)))   # 중복 제거, 순서 유지
    reply = _call(FOREIGN_FIX_PROMPT.format(context=joined[:600], words="\n".join(words)),
                  provider, model, api_key)

    mapping = {}
    for line in reply.splitlines():
        src, _, dst = line.partition("=")
        src, dst = _clean(src).strip(), dst.strip()
        if src in words and dst and not FOREIGN_RE.search(dst):
            mapping[src] = dst
    if len(mapping) < len(words):
        return None

    out = dict(parsed)
    for key in ("ko_title", "summary", "why"):
        value = out.get(key)
        if value:
            for src, dst in mapping.items():
                value = value.replace(src, dst)
            out[key] = value

    fixed = " ".join(filter(None, [out.get("ko_title"), out.get("summary"), out.get("why")]))
    return None if FOREIGN_RE.search(fixed) else out


# ---------------------------------------------------------------- public
MAX_429_RETRIES = 2     # 429 재시도 상한 — 넘으면 서킷 브레이커 (SPEC 1.6)
MAX_RETRY_WAIT = 90     # Retry-After가 이보다 길면 기다리지 않고 바로 포기


def summarize_all(articles: list[dict], provider: str | None = None,
                  model: str | None = None, pause: float = 4.0,
                  max_calls: int = 50) -> list[dict]:
    """랭킹 순서대로 요약. 반환 기사의 llm_done이 False면 게시·seen 등록 금지."""
    provider = (provider or PROVIDER).lower()
    if provider not in DEFAULT_MODELS:
        raise ValueError(f"알 수 없는 공급자: {provider} (groq / openrouter / gemini)")

    api_key = os.environ.get(KEY_ENV[provider])
    if not api_key:
        raise RuntimeError(
            f"{KEY_ENV[provider]}가 없습니다. GitHub Secrets 또는 로컬 환경변수에 넣어주세요."
        )
    model = model or os.environ.get("LLM_MODEL") or DEFAULT_MODELS[provider]
    print(f"[summarizer] {provider} · {model} · 호출 예산 {max_calls}회")

    calls = 0
    exhausted = False        # 서킷 브레이커 — 열리면 이후 호출을 시도조차 하지 않는다
    out = []

    for i, article in enumerate(articles, 1):
        if exhausted or calls >= max_calls:
            out.append({**article, "llm_done": False})
            continue

        body = (article.get("content") or article.get("description") or "").strip()
        prompt = PROMPT.format(
            title=article["title"],
            source=article.get("source", ""),
            # 분당 토큰 제한(Groq 무료 12K TPM)에 걸리지 않도록 본문을 2천 자로 자른다
            body=body[:2000] if body else "(본문 없음 — 제목만으로 작성하되 추측하지 마라)",
        )

        parsed = None
        retries_429 = 0
        attempt = 0
        while attempt < 3:
            if calls >= max_calls:
                exhausted = True
                break
            try:
                calls += 1
                candidate = _parse(_call(prompt, provider, model, api_key))
                if candidate["ko_title"] or candidate["summary"]:
                    joined = " ".join(filter(None, [candidate["ko_title"] or "",
                                                    candidate["summary"], candidate["why"]]))
                    # 외국 문자는 절대 수용하지 않는다: 재생성 1회 → 번역·일괄 치환 1회
                    # → 그래도 남으면 미게시(llm_done=False, 다음 실행에서 재시도).
                    if FOREIGN_RE.search(joined):
                        if attempt < 1:
                            print("  · 외국 문자 섞임 — 재생성")
                            attempt += 1
                            continue
                        if calls < max_calls:
                            calls += 1
                            fixed = _translate_foreign(candidate, provider, model, api_key)
                            if fixed is not None:
                                print("  · 외국 문자 번역 치환 성공")
                                parsed = fixed
                                break
                        print("  · 외국 문자 잔존 — 이번 회차 미게시 (다음 실행에서 재시도)")
                        break
                    parsed = candidate
                    break
                print(f"  · 파싱 실패, 재시도 {attempt + 1}")
                attempt += 1
            except RateLimited as e:
                retries_429 += 1
                if retries_429 > MAX_429_RETRIES or e.wait > MAX_RETRY_WAIT:
                    exhausted = True
                    break
                print(f"  · 한도(429) — {e.wait:.0f}초 대기 후 재시도 {retries_429}/{MAX_429_RETRIES}")
                time.sleep(e.wait + 1)
            except Exception as e:
                print(f"  · 오류({attempt + 1}/3): {e}")
                attempt += 1
                time.sleep(4 * attempt)

        if parsed is None:
            out.append({**article, "llm_done": False})
            if exhausted:
                done = sum(1 for a in out if a.get("llm_done"))
                remain = len(articles) - i + 1
                print(f"[한도] 요약 {done}/{len(articles)}건 완료 후 한도 도달 — "
                      f"나머지 {remain}건은 이번 회차 미게시, 다음 실행에서 재탐지")
            else:
                print(f"[{i}/{len(articles)}] 실패 · {article['title'][:45]}")
            continue

        print(f"[{i}/{len(articles)}] OK · {article['title'][:45]}")
        out.append({**article, **parsed, "llm_done": True})
        time.sleep(pause)          # 분당 토큰 제한(TPM) 여유를 둔다

    ok = sum(1 for a in out if a.get("llm_done"))
    print(f"[summarizer] 성공 {ok}/{len(out)} · 호출 {calls}회")
    return out
