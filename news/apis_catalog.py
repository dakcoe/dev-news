"""public-apis · public-apis-4Kr README를 파싱해 API 카탈로그 스냅샷을 만든다.

뉴스 기사 파이프라인(요약·seen·아카이브)과 완전히 분리된 별도 산출물이다 —
기사가 아니라 목록이므로 LLM 예산을 쓰지 않고, 매 회차 전체를 다시 긁어
docs/data/apis.json 을 통째로 교체한다 (append 아님).

파싱 규칙
- 목차 헤딩(`## Index` / `## 목차`) **이후**의 `### 카테고리` 아래 표 행만 수집.
  본가 README 상단의 스폰서 표가 목차 앞에 있어서 이 규칙 하나로 걸러진다.
- 표 행은 첫 셀이 `[이름](링크)` 인 행만 인정 — 헤더·구분선은 자연히 빠진다.
- 본가는 5열(Auth·HTTPS·CORS), 한국판은 3열(인증)이지만 둘 다
  "링크 | 설명 | 인증"까지만 쓰므로 파서 하나로 처리한다.

무료 LLM 소스(api-free-llm-source)
- public-apis 는 커뮤니티 갱신이 느려 Groq·OpenRouter 같은 최신 LLM API 가
  거의 없다. mnfst/awesome-free-llm-apis 는 같은 정보를 **유지보수되는
  data.json** 으로 내주므로 README 파싱 대신 스키마를 그대로 받는다.
- 화면에는 제공자 1줄로 접어 넣는다 — 모델별 행으로 펼치면 항목 수가
  10배로 늘어 기존 아코디언이 무너진다. 모델 정보는 대표 한도로 요약한다.
- README 의 AI/ML 카테고리와 겹치는 제공자(Groq·Gemini·Hugging Face 등)는
  README 쪽을 지운다. 다만 이름만 보고 전역으로 지우면 안 된다 —
  `Cryptocurrency | Gemini` 는 암호화폐 거래소라 Google Gemini 와 무관하다.
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from datetime import datetime

import requests

from news import api_health

from news.core.common import KST  # noqa: E402  (상수 재노출)
HEADERS = {"User-Agent": "dev-news/1.0 (personal feed aggregator)"}

SOURCES = [
    {"id": "kr", "label": "한국판", "kind": "readme",
     "url": "https://raw.githubusercontent.com/yybmion/public-apis-4Kr/main/README.md",
     "home": "https://github.com/yybmion/public-apis-4Kr"},
    {"id": "global", "label": "Public APIs", "kind": "readme",
     "url": "https://raw.githubusercontent.com/public-apis/public-apis/master/README.md",
     "home": "https://github.com/public-apis/public-apis"},
    {"id": "llm", "label": "무료 LLM", "kind": "llm_json",
     "url": "https://raw.githubusercontent.com/mnfst/awesome-free-llm-apis/main/data.json",
     "home": "https://github.com/mnfst/awesome-free-llm-apis"},
]

LLM_CAT = "AI · LLM"

# README 형식이 바뀌어 파싱이 거의 안 되는 회차에 기존 파일을 덮어쓰지 않기 위한
# 소스별 최소 건수. 실측(2026-08): global 1,400+ · kr 300+ · llm 17.
MIN_COUNT = {"global": 300, "kr": 50, "llm": 10}

_TOC_RE = re.compile(r"^##\s*(Index|목차)\b", re.I)
_CAT_RE = re.compile(r"^###\s+(.+)")
_ROW_RE = re.compile(r"^\|\s*\[([^\]]+)\]\((https?://[^)\s]+)[^)]*\)\s*\|(.*)")

# 중복 제거를 적용할 카테고리 판정 (api-llm-dedupe).
# template.html 의 'AI · LLM' 대분류 정규식과 같은 규칙을 파이썬으로 옮긴 것 —
# 한쪽만 고치면 화면 분류와 중복 제거 범위가 어긋나므로 함께 유지한다.
_AI_CAT_RE = re.compile(r"머신러닝|인공지능|\bAI\b|machine.?learning|\bnlp\b|\bllm\b", re.I)
_NORM_RE = re.compile(r"[^0-9a-z가-힣]+")


def parse(md: str, source_id: str) -> list[dict]:
    apis: list[dict] = []
    cat = None
    after_toc = False
    for line in md.splitlines():
        if _TOC_RE.match(line):
            after_toc = True
            continue
        m = _CAT_RE.match(line)
        if m:
            cat = m.group(1).strip() if after_toc else None
            continue
        if not cat:
            continue
        r = _ROW_RE.match(line.strip())
        if not r:
            continue
        name, url, rest = r.group(1).strip(), r.group(2).strip(), r.group(3)
        cells = [c.strip() for c in rest.strip("|").split("|")]
        desc = cells[0] if cells else ""
        auth = cells[1].strip("`").strip() if len(cells) > 1 else ""
        if auth.lower() == "no":
            auth = ""                      # 빈 값 = 인증 불필요
        apis.append({"name": name, "url": url, "desc": desc,
                     "auth": auth, "cat": cat, "src": source_id})
    return apis


def parse_llm_json(data: dict, source_id: str) -> list[dict]:
    """data.json 의 providers 를 제공자 1건씩으로 접는다.

    대표 한도는 모델 rateLimit 의 최빈값 — 실측상 17개 제공자 중 13곳은 모든
    모델이 같은 한도이고, 나머지도 최빈값이 그 제공자의 기본 한도다.
    """
    apis: list[dict] = []
    for p in data.get("providers", []):
        name, url = (p.get("name") or "").strip(), (p.get("url") or "").strip()
        if not name or not url:
            continue                    # 이름·링크 없는 행은 화면에서 쓸모가 없다
        models = p.get("models") or []
        limits = [m.get("rateLimit") for m in models if m.get("rateLimit")]
        parts = [(p.get("description") or "").strip()]
        if limits:
            parts.append(f"대표 한도 {Counter(limits).most_common(1)[0][0]}")
        if models:
            names = ", ".join(str(m.get("name") or m.get("id") or "") for m in models[:3])
            parts.append(f"모델 {len(models)}개 ({names}{'…' if len(models) > 3 else ''})")
        apis.append({"name": name, "url": url,
                     "desc": " · ".join(x for x in parts if x),
                     "auth": "apiKey",   # 무료 티어라도 키는 필요 — 빈 값이면 '인증 불필요' 배지가 붙는다
                     "cat": LLM_CAT, "src": source_id})
    return apis


def _norm_name(name: str) -> str:
    """이름 비교용 정규화 — 'Hugging Face' / 'hugging-face' 를 같게 본다."""
    return _NORM_RE.sub("", name.lower())


def dedupe_llm_overlap(readme_apis: list[dict], llm_apis: list[dict]) -> list[dict]:
    """README 쪽 AI/ML 항목 중 무료 LLM 소스와 겹치는 것을 지운다.

    LLM 소스가 이긴다 — 대표 한도·모델 수까지 있어 정보량이 많고 일 단위로
    갱신된다. 제거는 AI/ML 카테고리 안에서만 한다: 이름이 같아도 다른 API 인
    경우(Cryptocurrency 의 Gemini)를 지우면 안 되기 때문이다.
    """
    known = {_norm_name(a["name"]) for a in llm_apis}
    return [a for a in readme_apis
            if not (_AI_CAT_RE.search(a["cat"]) and _norm_name(a["name"]) in known)]


def build_catalog() -> dict:
    """세 소스를 받아 카탈로그 dict를 만든다. 실패는 예외로 올린다."""
    by_source: dict[str, list[dict]] = {}
    for s in SOURCES:
        resp = requests.get(s["url"], headers=HEADERS, timeout=20)
        resp.raise_for_status()
        apis = (parse_llm_json(resp.json(), s["id"]) if s["kind"] == "llm_json"
                else parse(resp.text, s["id"]))
        floor = MIN_COUNT.get(s["id"], 0)
        if len(apis) < floor:
            raise ValueError(f"{s['label']} 파싱 {len(apis)}건 < 최소 {floor}건 — 소스 형식 변경 의심")
        by_source[s["id"]] = apis

    # 중복 제거는 방어선(MIN_COUNT) 통과 뒤에 한다 — 제거분 때문에 회차가 죽으면 안 된다
    llm_apis = [a for s in SOURCES if s["kind"] == "llm_json" for a in by_source[s["id"]]]
    for s in SOURCES:
        if s["kind"] != "llm_json":
            by_source[s["id"]] = dedupe_llm_overlap(by_source[s["id"]], llm_apis)

    all_apis: list[dict] = []
    sources = []
    for s in SOURCES:
        apis = by_source[s["id"]]
        sources.append({"id": s["id"], "label": s["label"],
                        "home": s["home"], "count": len(apis)})
        all_apis.extend(apis)
    return {"updated": datetime.now(KST).isoformat(),
            "sources": sources, "apis": all_apis}


def sync(out_path: str, health: dict | None = None,
         cache_path: str | None = None) -> bool:
    """카탈로그를 갱신한다. 실패 시 기존 파일을 그대로 두고 False.

    회차를 죽이지 않는다 — 뉴스 게시와 무관한 부가 산출물이므로 실패해도
    로그만 남기고 지나간다. 다음 회차가 다시 시도한다.

    링크 생존 확인(api-link-health)은 그보다 한 단계 더 무르게 다룬다:
    확인이 통째로 터져도 확인 전 목록을 그대로 내보낸다. 죽은 링크가 며칠 더
    남는 것보다 목록이 통째로 사라지는 쪽이 나쁘다.
    """
    try:
        catalog = build_catalog()
    except Exception as e:
        print(f"[apis] 카탈로그 갱신 실패 — 기존 파일 유지: {e}")
        return False

    if (health or {}).get("enabled"):
        try:
            kept, summary = api_health.run(
                catalog["apis"],
                cache_path or os.path.join("data", "api_health.json"),
                health)
            catalog["apis"] = kept
            catalog["health"] = summary
            counts = Counter(a["src"] for a in kept)
            for s in catalog["sources"]:
                s["count"] = counts.get(s["id"], 0)
            print(f"[apis] 링크 확인 {summary['checked']}건 "
                  f"(살아있음 {summary['ok']} · 죽음 {summary['dead']} · "
                  f"보류 {summary['unknown']}) → 목록에서 제외 {summary['dropped']}건")
        except Exception as e:
            print(f"[apis] 링크 확인 실패 — 확인 없이 목록을 내보낸다: {e}")

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False)
    counts = " · ".join(f"{s['label']} {s['count']}건" for s in catalog["sources"])
    print(f"[apis] 카탈로그 갱신: {counts}")
    return True
