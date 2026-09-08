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
               "desc": "github.com/trending 일간 + Trendshift 일간 순위 — 같은 저장소는 한 건으로 합쳐진다"},
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
    if not _CLIENT_RE.match(client):
        print("[ads] client는 ca-pub-숫자여야 합니다 — 광고를 끕니다")
        return None
    # 심사 단계에서는 slot이 없다. 광고 단위는 승인 뒤에 만들기 때문이다.
    # 그런데 구글은 로더 스크립트가 head에 있어야 사이트를 확인해 준다. 그래서
    # slot이 비면 로더만 넣고 광고 자리는 그리지 않는다(빈 ins는 오류가 된다).
    # 값이 있는데 형식이 틀린 경우는 오타이므로 예전처럼 전부 끈다.
    if slot and not _SLOT_RE.match(slot):
        print("[ads] slot은 숫자여야 합니다 — 광고를 끕니다")
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


# ---------------------------------------------------------------- SEO
# 이 페이지는 기사를 JS 배열로 싣고 브라우저가 그린다. 그래서 크롤러가 받는
# HTML 본문에 글자가 없었다(실측 9자). 구글이 JS를 실행하긴 하지만 순서가
# 밀리고 보장되지 않는다 — 2026-09-07 기준 색인 0건이었다.
#
# 그래서 최근 기사만 정적 마크업으로 같이 굽는다. 스크립트가 로드되면 같은
# 내용을 대화형 화면으로 대체하므로 사람이 보는 것과 크롤러가 읽는 것이
# 다르지 않다. 전부 넣으면 파일이 배로 커지므로 최근 것만 넣는다.
SEO_ITEMS = 120
CNAME_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "docs", "CNAME")
FALLBACK_URL = "https://dakcoe.github.io/dev-news"


def site_url() -> str:
    """사이트 주소. docs/CNAME이 단일 출처다(없으면 옛 Pages 주소)."""
    try:
        with open(CNAME_PATH, encoding="utf-8") as f:
            host = f.read().strip()
        return f"https://{host}" if host else FALLBACK_URL
    except OSError:
        return FALLBACK_URL


def _esc(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _seo_html(view_model: list[dict], collected: datetime, limit: int = SEO_ITEMS) -> str:
    """스크립트가 실행되기 전에 보이는 화면.

    ⚠️ **JS가 그리는 화면과 같은 마크업을 써야 한다.** 처음에 다른 모양으로
    그렸더니 스크립트가 뜨는 순간 사이드바가 생기고 카드로 바뀌면서 화면이
    통째로 흔들렸다 — 스타일이 늦게 오는 것처럼 보인다. 그래서 h1·.sub·
    .status·.layout·.row을 그대로 쓴다. 교체돼도 자리가 그대로다.
    """
    items = sorted(view_model, key=lambda d: d.get("batch") or "", reverse=True)[:limit]
    batches = len({d.get("batch") for d in view_model if d.get("batch")})
    rows = []
    for d in items:
        meta = ['<span class="s">' + _esc(d.get("from") or d.get("src") or "") + "</span>"]
        if d.get("batchLabel"):
            meta.append('<span class="sep">·</span><span>' + _esc(d["batchLabel"]) + "</span>")
        rows.append(
            '<div class="row"><div></div><div class="mid">'
            f'<h2 class="rt"><a href="{_esc(d.get("url") or "")}" rel="noopener">'
            f'{_esc(d.get("title") or "")}</a></h2>'
            '<div class="rm">' + "".join(meta) + "</div>"
            + (f'<div class="snip">{_esc(d["snip"])}</div>' if d.get("snip") else "")
            + "</div><div></div><div></div></div>")
    return (
        "<h1>오늘의 뉴스</h1>"
        '<div class="sub">매일 00시·08시·16시에 수집합니다. '
        "30일 지난 기사는 검색으로 찾을 수 있습니다 "
        f"(최근 {batches}회차)</div>"
        '<div class="status"><div class="stmeta">'
        f'<b>최근 30일 {len(view_model)}건</b> · 수집 {collected.strftime("%Y년 %m월 %d일")}<br>'
        f'<span class="l2">회차 {batches}개 · 해커뉴스·GitHub 트렌딩·Lobsters·'
        "dev.to·긱뉴스에서 모읍니다</span></div></div>"
        # 검색·필터 바 자리. 높이를 잡아두지 않으면 스크립트가 뜰 때 목록이 밀린다.
        '<div class="bar"><div class="search">'
        '<input placeholder="검색 (아카이브 포함)…" disabled></div></div>'
        '<div class="layout"><div class="facet" style="min-height:420px"></div>'
        '<div class="feed">' + "".join(rows) + "</div></div>")


def _meta_desc(view_model: list[dict]) -> str:
    """검색 결과에 뜨는 한 줄. 오늘 실린 제목 몇 개를 붙여 매일 달라지게 한다."""
    titles = [d.get("title", "") for d in view_model[:3] if d.get("title")]
    base = "매일 세 번 모으는 개발·AI 뉴스. 해커뉴스, GitHub 트렌딩, Lobsters 등을 한국어로."
    return _esc((base + " 오늘: " + " / ".join(titles))[:160]) if titles else _esc(base)


def _jsonld(view_model: list[dict], collected: datetime, limit: int = SEO_ITEMS) -> str:
    """구조화된 데이터. 이 페이지는 '남의 기사로 만든 목록'이므로 ItemList다.

    ⚠️ NewsArticle로 표시하지 않는다. 기사를 우리가 쓴 게 아니라서 사실과 다르고,
    구글 구조화 데이터 정책의 잘못된 표시에 걸린다.
    """
    items = sorted(view_model, key=lambda d: d.get("batch") or "", reverse=True)[:limit]
    base = site_url()
    elements = []
    for i, d in enumerate(items, 1):
        if not d.get("url"):
            continue
        elements.append({"@type": "ListItem", "position": i,
                         "url": d["url"], "name": d.get("title") or ""})
    data = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "WebSite", "@id": base + "/#site", "url": base + "/",
             "name": "dev-news", "inLanguage": "ko",
             "description": "매일 세 번 모으는 개발·AI 뉴스"},
            {"@type": "CollectionPage", "@id": base + "/#page", "url": base + "/",
             "isPartOf": {"@id": base + "/#site"},
             "name": f'개발·AI 뉴스 · {collected.strftime("%Y-%m-%d")}',
             "inLanguage": "ko",
             "dateModified": collected.isoformat(timespec="seconds"),
             "mainEntity": {"@type": "ItemList", "numberOfItems": len(elements),
                            "itemListOrder": "https://schema.org/ItemListOrderDescending",
                            "itemListElement": elements}},
        ],
    }
    return ('<script type="application/ld+json">'
            + json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            + "</script>")


# 이름을 적어 두는 크롤러들. `User-agent: *`가 이미 전체를 허용하지만,
# 이 봇들은 "이름이 안 적혀 있으면 안 긁는다"는 정책을 쓰거나(Google-Extended,
# Applebot-Extended) 운영자가 막았는지를 이름 단위로 확인한다. 명시해 두면
# AI 답변의 출처로 인용될 길이 열린다 — 이게 GEO의 기술적 절반이다.
AI_AGENTS = [
    "Googlebot", "Google-Extended", "Bingbot", "Yeti",          # 검색 + 네이버
    "GPTBot", "OAI-SearchBot", "ChatGPT-User",                  # OpenAI
    "ClaudeBot", "Claude-User", "Claude-SearchBot",             # Anthropic
    "PerplexityBot", "Perplexity-User",                         # Perplexity
    "Applebot", "Applebot-Extended", "CCBot", "Amazonbot",
]


def write_seo_files(out_dir: str, collected: datetime) -> None:
    """robots.txt · sitemap.xml · llms.txt.

    한 장짜리 사이트라 사이트맵은 한 줄이다. llms.txt는 AI가 사이트를 요약할 때
    읽어가는 안내문으로, 표준은 아니지만 파일 하나 값이면 손해 볼 게 없다.
    """
    base = site_url()
    with open(os.path.join(out_dir, "robots.txt"), "w", encoding="utf-8") as f:
        f.write("User-agent: *\nAllow: /\n\n")
        for ua in AI_AGENTS:
            f.write(f"User-agent: {ua}\nAllow: /\n\n")
        f.write(f"Sitemap: {base}/sitemap.xml\n")
    with open(os.path.join(out_dir, "llms.txt"), "w", encoding="utf-8") as f:
        f.write(
            "# dev-news\n\n"
            "> 해커뉴스·GitHub 트렌딩·Lobsters·dev.to·긱뉴스에서 개발과 AI 소식을 "
            "매일 세 번(00시·08시·16시 KST) 모아 한국어로 요약하는 사이트다.\n\n"
            "기사마다 두세 문장 요약과 '왜 중요한가' 한 단락을 붙인다. 원문은 각 "
            "출처로 연결되며, 이 사이트가 기사를 직접 쓰지는 않는다.\n\n"
            "## 페이지\n\n"
            f"- [오늘의 뉴스]({base}/): 최근 30일치 목록. 출처·태그·기간으로 거르고 "
            "전체 아카이브를 검색할 수 있다.\n"
            f"- [무료 API 목록]({base}/#api): 공개 API 카탈로그. 회차마다 링크 생존을 "
            "확인해 죽은 링크는 뺀다.\n\n"
            "## 인용\n\n"
            "요약문은 이 사이트가 생성한 것이므로 dev-news를 출처로 적어 달라. "
            "기사 내용 자체는 각 원문 출처를 따른다.\n"
        )
    with open(os.path.join(out_dir, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                f'  <url><loc>{base}/</loc>'
                f'<lastmod>{collected.date().isoformat()}</lastmod>'
                '<changefreq>daily</changefreq></url>\n'
                '</urlset>\n')


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

    view_model = to_view_model(articles)

    with open(TEMPLATE, encoding="utf-8") as f:
        html = f.read()

    html = (html
            .replace("__DATA_JSON__", json.dumps(view_model, ensure_ascii=False))
            .replace("__SRC_JSON__", json.dumps(sources, ensure_ascii=False))
            .replace("__TAG_JSON__", json.dumps(
                {tid: {"label": spec["label"], "group": spec["group"]}
                 for tid, spec in tag_vocab.VOCAB.items()},
                ensure_ascii=False))
            .replace("__COLLECTED_LABEL__", collected.strftime("%p %I:%M").replace("AM", "오전").replace("PM", "오후"))
            .replace("__COLLECTED__", collected.isoformat())
            .replace("__DATE__", collected.strftime("%Y-%m-%d"))
            .replace("__SEO_HTML__", _seo_html(view_model, collected))
            .replace("__JSONLD__", _jsonld(view_model, collected))
            .replace("__META_DESC__", _meta_desc(view_model))
            .replace("__SITE_URL__", site_url())
            .replace("__ADS_HEAD__", _ads_head(ads_cfg))
            .replace("__ADS_JSON__", json.dumps(ads_cfg, ensure_ascii=False)))

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[render] {out_path} · 기사 {len(articles)}건")
    return out_path
