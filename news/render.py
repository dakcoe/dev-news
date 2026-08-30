"""수집·요약된 기사 목록을 정적 HTML 한 장으로 렌더링한다."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone

from news.core import tags as tag_vocab

from news.core.common import KST  # noqa: E402  (상수 재노출)
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "template.html")

# 화면에 쓰이는 출처 메타데이터. config.yaml의 sources와 키를 맞춘다.
SOURCE_META = {
    "hackernews": {"name": "Hacker News", "color": "#ff6600",
                   "desc": "HN Firebase API에서 Top Stories 수집 · 상위 100개에서 AI/개발 뉴스 필터링"},
    "github": {"name": "GitHub Trending", "color": "#1f2328",
               "desc": "일간 트렌딩 저장소에서 개발·AI 관련 프로젝트 수집"},
    "lobsters": {"name": "Lobste.rs", "color": "#ac130d",
                 "desc": "hottest.json에서 상위 스토리 수집"},
    "devto": {"name": "dev.to", "color": "#3b49df",
              "desc": "javascript · python · ai · rust · devops 등 태그별 rising 글"},
    "reddit": {"name": "Reddit", "color": "#ff4500",
               "desc": "r/LocalLLaMA · r/ClaudeAI · r/MachineLearning 등 hot 포스트"},
    "geeknews": {"name": "긱뉴스", "color": "#2f7de0",
                 "desc": "news.hada.io RSS — 한국 개발자 커뮤니티 소식"},
    "rss": {"name": "블로그 · RSS", "color": "#6b5bd2",
            "desc": "config.yaml의 feeds 목록 — 공식 블로그와 기술 매체"},
    "anthropic": {"name": "Anthropic", "color": "#c96442",
                  "desc": "anthropic.com/news · /engineering 직접 파싱 (RSS 미제공)"},
}


# 광고 설정 검증 (add-ad-slot).
# 형식이 조금이라도 어긋나면 광고를 끈다 — 검증 없이 head에 심으면 config 한 줄로
# 남의 스크립트를 페이지에 주입하는 통로가 된다.
_CLIENT_RE = re.compile(r"^ca-pub-\d{10,20}$")
_SLOT_RE = re.compile(r"^\d{6,20}$")
_ADS_MAX = 3                        # 사이드 레일에 쌓을 수 있는 광고 개수 상한

ADSENSE_SRC = "https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js"


def _ads_config(ads: object) -> dict | None:
    """config.yaml의 ads 블록을 검증해 템플릿에 넘길 형태로 줄인다.

    쓸 수 없는 설정이면 None — 광고 없이 페이지가 정상적으로 나가는 쪽이
    깨진 광고 코드가 실리는 것보다 낫다.
    """
    if not isinstance(ads, dict) or not ads.get("enabled"):
        return None
    try:
        count = min(_ADS_MAX, int(ads.get("count", 1)))
    except (TypeError, ValueError):
        print("[ads] count가 숫자가 아닙니다 — 광고를 끕니다")
        return None
    if count < 1:
        return None

    provider = str(ads.get("provider") or "placeholder").strip()
    if provider == "placeholder":
        return {"provider": "placeholder", "count": count}
    if provider != "adsense":
        print(f"[ads] 모르는 provider '{provider}' — 광고를 끕니다")
        return None

    client = str(ads.get("client") or "").strip()
    slot = str(ads.get("slot") or "").strip()
    if not _CLIENT_RE.match(client) or not _SLOT_RE.match(slot):
        print("[ads] client는 ca-pub-숫자, slot은 숫자여야 합니다 — 광고를 끕니다")
        return None
    return {"provider": "adsense", "client": client, "slot": slot, "count": count}


def _ads_head(cfg: dict | None) -> str:
    """애드센스 로더는 head에 한 번만 넣는다. client는 정규식을 통과한 값뿐이다."""
    if not cfg or cfg["provider"] != "adsense":
        return ""
    return (f'<script async src="{ADSENSE_SRC}?client={cfg["client"]}" '
            f'crossorigin="anonymous"></script>')


def _pub_iso(article: dict) -> str:
    ts = article.get("published_at")
    if ts is None:
        return datetime.now(timezone.utc).isoformat()
    try:
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(float(ts), timezone.utc).isoformat()
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


def _first_sentences(text: str, limit: int = 140) -> str:
    text = (text or "").strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    cut = text[:limit]
    dot = max(cut.rfind("다."), cut.rfind(". "))
    return (cut[: dot + 1] if dot > 60 else cut.rstrip() + "…")


# 상세 패널 전용 필드(body·why)를 인라인할 기간. 이보다 오래된 기사는 상세를 열 때
# 월별 샤드에서 가져온다 (template.html의 openArchived 경로 재사용).
# 목록·검색·필터는 snip만 쓰므로 화면 동작은 달라지지 않는다.
INLINE_DAYS = 3


def to_view_model(articles: list[dict], inline_days: int = INLINE_DAYS) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=inline_days)).timestamp() if inline_days else None
    out = []
    for a in articles:
        summary = a.get("summary") or a.get("description") or ""
        # 페이월·영상·JS 전용 페이지는 본문 추출이 안 돼 요약이 비는 게 정상 —
        # "생성 실패"가 아니라 본문 미공개 안내를 보여준다 (fix-empty-summary-label).
        body_paras = [p.strip() for p in summary.split("\n") if p.strip()] or ["(본문이 공개되지 않은 기사 — 원문을 확인하세요)"]
        inline = True
        if cutoff is not None:
            try:
                inline = datetime.fromisoformat(a["batch"]).timestamp() >= cutoff
            except Exception:
                inline = True          # 회차를 모르면 안전하게 인라인
        out.append({
            "batch": a.get("batch", ""),
            "batchLabel": a.get("batch_label", ""),
            "month": (a.get("batch", "") or "")[:7],
            "delta": a.get("delta_stars"),        # GitHub 전일 대비 스타 증가량 (SPEC 1.5)
            "src": a.get("source", "media"),
            "title": a.get("ko_title") or a.get("title", ""),
            # RSS는 피드 이름을, 서브레딧은 r/이름을 출처로 표시한다
            "from": (a.get("from") or a.get("feed")
                     or (f"r/{a['subreddit']}" if a.get("subreddit") else None)
                     or SOURCE_META.get(a.get("source", ""), {}).get("name", a.get("source", ""))),
            "url": a.get("url", ""),
            "img": a.get("image") or "",
            "score": int(a.get("upvotes") or 0),
            "cm": int(a.get("comments") or 0),
            "pub": _pub_iso(a),
            "tags": a.get("tags") or [],
            "snip": _first_sentences(summary),
        })
        if inline:
            out[-1]["body"] = "".join(f"<p>{p}</p>" for p in body_paras)
            out[-1]["why"] = a.get("why") or ""
    return out


def render(articles: list[dict], out_path: str, collected: datetime | None = None,
           enabled: dict[str, bool] | None = None, ads: dict | None = None) -> str:
    """enabled: config.yaml의 sources. 토글은 '설정에서 켜졌는지'를 나타낸다.

    오늘 결과에 그 출처 글이 없을 수도 있으므로(점수에서 밀렸거나 새 글이 없거나)
    '켜짐 여부'와 '오늘 몇 건'은 별개로 표시한다.
    """
    collected = collected or datetime.now(KST)
    enabled = enabled or {}
    ads_cfg = _ads_config(ads)

    sources = {k: {"name": v["name"], "color": v["color"], "desc": v["desc"],
                   "on": bool(enabled.get(k, True))}
               for k, v in SOURCE_META.items()}

    with open(TEMPLATE, encoding="utf-8") as f:
        html = f.read()

    html = (html
            .replace("__DATA_JSON__", json.dumps(to_view_model(articles), ensure_ascii=False))
            .replace("__SRC_JSON__", json.dumps(sources, ensure_ascii=False))
            .replace("__TAG_JSON__", json.dumps(
                {tid: {"label": spec["label"], "group": spec["group"]}
                 for tid, spec in tag_vocab.VOCAB.items()},
                ensure_ascii=False))
            .replace("__COLLECTED_LABEL__", collected.strftime("%p %I:%M").replace("AM", "오전").replace("PM", "오후"))
            .replace("__COLLECTED__", collected.isoformat())
            .replace("__DATE__", collected.strftime("%Y-%m-%d"))
            .replace("__ADS_HEAD__", _ads_head(ads_cfg))
            .replace("__ADS_JSON__", json.dumps(ads_cfg, ensure_ascii=False)))

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[render] {out_path} · 기사 {len(articles)}건")
    return out_path
