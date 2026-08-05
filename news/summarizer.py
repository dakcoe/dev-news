"""제목 번역 · 3~5문장 요약 · '왜 중요한가' 한 줄 생성.

공급자는 환경변수 LLM_PROVIDER로 바꾼다.

  groq        (기본) 무료 · 카드 없음 · 하루 1,000회   GROQ_API_KEY
  openrouter        무료 모델 하루 50회               OPENROUTER_API_KEY
  gemini            한국어 품질 최상                   GEMINI_API_KEY

모델을 바꾸려면 LLM_MODEL 환경변수를 지정한다.
"""
from __future__ import annotations

import os
import re
import time

import requests

PROVIDER = os.environ.get("LLM_PROVIDER", "groq").lower()

DEFAULT_MODELS = {
    "groq": "llama-3.3-70b-versatile",
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

SYSTEM = "너는 한국인 개발자를 위한 기술 뉴스 브리핑 편집자다. 지시한 형식만 출력하고 다른 말은 절대 붙이지 않는다."

PROMPT = """아래 기사를 다음 형식으로만 출력해라.

번역제목: (제목이 외국어면 자연스러운 한국어로. 이미 한국어면 그대로. GitHub 저장소면 "owner / repo — 한 줄 설명" 형태)
요약: (3~5문장. 무엇이 발표·공개됐고 기술적으로 무엇이 달라졌는지. 숫자가 있으면 숫자를 살려라. 원문에 없는 내용은 절대 지어내지 마라)
왜중요: (한 문장. 개인 프로젝트를 운영하는 개발자에게 어떤 의미인지)

[기사]
제목: {title}
출처: {source}
본문: {body}
"""

LABELS = {"번역제목": "ko_title", "요약": "summary", "왜중요": "why"}


def _clean(line: str) -> str:
    line = re.sub(r"^#+\s*", "", line.strip())
    return line.replace("**", "").replace("*", "")


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
    return {k: (" ".join(v).strip() or None) for k, v in buf.items()}


# ---------------------------------------------------------------- providers
class RateLimited(Exception):
    """429. 서버가 알려준 대기 시간을 담는다."""

    def __init__(self, wait: float):
        super().__init__(f"rate limit (429) — {wait:.0f}초 대기")
        self.wait = wait


def _retry_after(resp: requests.Response) -> float:
    """Retry-After 헤더를 초 단위로. 없으면 20초."""
    raw = resp.headers.get("retry-after") or resp.headers.get("x-ratelimit-reset-tokens", "")
    m = re.match(r"^\s*([\d.]+)\s*(ms|m|s)?\s*$", str(raw))
    if m:
        value, unit = float(m.group(1)), (m.group(2) or "s")
        return {"ms": value / 1000, "s": value, "m": value * 60}[unit]
    return 20.0


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
    resp = requests.post(url, headers=headers, json=payload, timeout=90)
    if resp.status_code == 429:
        raise RateLimited(_retry_after(resp))
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    return resp.json()["choices"][0]["message"]["content"]


def _call_gemini(prompt: str, model: str, api_key: str) -> str:
    from google import genai  # 이 공급자를 쓸 때만 필요
    client = genai.Client(api_key=api_key)
    resp = client.models.generate_content(model=model, contents=SYSTEM + "\n\n" + prompt)
    return resp.text or ""


def _call(prompt: str, provider: str, model: str, api_key: str) -> str:
    if provider == "gemini":
        return _call_gemini(prompt, model, api_key)
    return _call_openai_compatible(prompt, model, api_key, ENDPOINTS[provider])


# ---------------------------------------------------------------- public
def summarize_all(articles: list[dict], provider: str | None = None,
                  model: str | None = None, pause: float = 4.0) -> list[dict]:
    provider = (provider or PROVIDER).lower()
    if provider not in DEFAULT_MODELS:
        raise ValueError(f"알 수 없는 공급자: {provider} (groq / openrouter / gemini)")

    api_key = os.environ.get(KEY_ENV[provider])
    if not api_key:
        raise RuntimeError(
            f"{KEY_ENV[provider]}가 없습니다. GitHub Secrets 또는 로컬 환경변수에 넣어주세요."
        )
    model = model or os.environ.get("LLM_MODEL") or DEFAULT_MODELS[provider]
    print(f"[summarizer] {provider} · {model}")

    out = []
    for i, article in enumerate(articles, 1):
        body = (article.get("content") or article.get("description") or "").strip()
        prompt = PROMPT.format(
            title=article["title"],
            source=article.get("source", ""),
            # 분당 토큰 제한(Groq 무료 12K TPM)에 걸리지 않도록 본문을 2천 자로 자른다
            body=body[:2000] if body else "(본문 없음 — 제목만으로 작성하되 추측하지 마라)",
        )

        parsed = {"ko_title": None, "summary": None, "why": None}
        for attempt in range(3):
            try:
                parsed = _parse(_call(prompt, provider, model, api_key))
                if parsed["ko_title"] or parsed["summary"]:
                    break
                print(f"  · 파싱 실패, 재시도 {attempt + 1}")
            except RateLimited as e:
                wait = min(e.wait + 1, 60)
                print(f"  · 한도 도달 — {wait:.0f}초 대기 후 재시도")
                time.sleep(wait)
            except Exception as e:
                print(f"  · 오류({attempt + 1}/3): {e}")
                time.sleep(4 * (attempt + 1))

        status = "OK" if parsed["summary"] else "실패"
        print(f"[{i}/{len(articles)}] {status} · {article['title'][:45]}")
        out.append({**article, **parsed})
        time.sleep(pause)          # 분당 토큰 제한(TPM) 여유를 둔다

    ok = sum(1 for a in out if a.get("summary"))
    print(f"[summarizer] 성공 {ok}/{len(out)}")
    return out
