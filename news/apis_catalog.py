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
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone

import requests

KST = timezone(timedelta(hours=9))
HEADERS = {"User-Agent": "dev-news/1.0 (personal feed aggregator)"}

SOURCES = [
    {"id": "kr", "label": "한국판",
     "readme": "https://raw.githubusercontent.com/yybmion/public-apis-4Kr/main/README.md",
     "home": "https://github.com/yybmion/public-apis-4Kr"},
    {"id": "global", "label": "Public APIs",
     "readme": "https://raw.githubusercontent.com/public-apis/public-apis/master/README.md",
     "home": "https://github.com/public-apis/public-apis"},
]

# README 형식이 바뀌어 파싱이 거의 안 되는 회차에 기존 파일을 덮어쓰지 않기 위한
# 소스별 최소 건수. 실측(2026-08): global 1,400+ · kr 300+.
MIN_COUNT = {"global": 300, "kr": 50}

_TOC_RE = re.compile(r"^##\s*(Index|목차)\b", re.I)
_CAT_RE = re.compile(r"^###\s+(.+)")
_ROW_RE = re.compile(r"^\|\s*\[([^\]]+)\]\((https?://[^)\s]+)[^)]*\)\s*\|(.*)")


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


def build_catalog() -> dict:
    """두 README를 받아 카탈로그 dict를 만든다. 실패는 예외로 올린다."""
    all_apis: list[dict] = []
    sources = []
    for s in SOURCES:
        resp = requests.get(s["readme"], headers=HEADERS, timeout=20)
        resp.raise_for_status()
        apis = parse(resp.text, s["id"])
        floor = MIN_COUNT.get(s["id"], 0)
        if len(apis) < floor:
            raise ValueError(f"{s['label']} 파싱 {len(apis)}건 < 최소 {floor}건 — README 형식 변경 의심")
        sources.append({"id": s["id"], "label": s["label"],
                        "home": s["home"], "count": len(apis)})
        all_apis.extend(apis)
    return {"updated": datetime.now(KST).isoformat(),
            "sources": sources, "apis": all_apis}


def sync(out_path: str) -> bool:
    """카탈로그를 갱신한다. 실패 시 기존 파일을 그대로 두고 False.

    회차를 죽이지 않는다 — 뉴스 게시와 무관한 부가 산출물이므로 실패해도
    로그만 남기고 지나간다. 다음 회차가 다시 시도한다.
    """
    try:
        catalog = build_catalog()
    except Exception as e:
        print(f"[apis] 카탈로그 갱신 실패 — 기존 파일 유지: {e}")
        return False
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False)
    counts = " · ".join(f"{s['label']} {s['count']}건" for s in catalog["sources"])
    print(f"[apis] 카탈로그 갱신: {counts}")
    return True
