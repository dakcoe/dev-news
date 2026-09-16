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
            "bodyFrom": a.get("body_from") or "",   # 'comments' 면 댓글로 쓴 요약
        })
        if inline:
            # ⚠️ HTML이 아니라 문단 목록으로 넘긴다. 예전에는 서버가 "<p>요약</p>"
            # 문자열을 만들어 보냈는데, 요약은 외부에서 온 글이라 그 안에 태그가
            # 섞이면 화면에서 그대로 실행됐다. 이스케이프할 지점이 아예 없는 구조라
            # 템플릿 쪽에서는 고칠 수도 없었다. 마크업은 한 곳에서만 만든다.
            out[-1]["paras"] = body_paras
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


def _json_for_script(obj) -> str:
    """<script> 안에 심어도 안전한 JSON.

    json.dumps는 HTML을 모른다. 기사 제목에 "</script>"가 들어 있으면 브라우저가
    거기서 스크립트를 끝내고 그 뒤를 마크업으로 읽는다 — 남의 기사 제목은 우리가
    정하는 값이 아니므로 실제로 들어올 수 있다. 파서가 태그로 볼 수 있는 조각만
    막으면 되고, 이스케이프한 뒤에도 JSON으로서는 같은 값이다.

    U+2028·U+2029는 JSON에서는 유효하지만 JS 소스에서는 줄바꿈이라 구문이 깨진다.
    """
    return (json.dumps(obj, ensure_ascii=False)
            .replace("</", "<\\/")
            .replace("<!--", "<\\!--")
            .replace("\u2028", "\\u2028")
            .replace("\u2029", "\\u2029"))


def _safe_url(url: str) -> str:
    """href·src에 넣어도 되는 주소만 통과시킨다.

    "javascript:alert(1)" 같은 주소가 링크에 실리면 클릭 한 번에 실행된다.
    출처에서 받은 값을 그대로 쓰므로 스킴을 직접 확인한다.
    """
    u = (url or "").strip()
    return u if u[:7].lower() == "http://" or u[:8].lower() == "https://" else ""


def _esc(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


# 소개 화면 글. 앱 안(JS)과 정적 페이지(/about/, /privacy/)가 같은 글을 쓴다 —
# 두 곳에 따로 두면 한쪽만 고쳐져 어긋난다. 후원·문의 버튼과 프로필은 about 설정에서.
def about_copy(enabled: dict | None) -> list[dict]:
    names = ", ".join(m["name"] for k, m in SOURCE_META.items() if (enabled or {}).get(k, True))
    return [
        {"id": "intro", "title": "사이트 소개",
         "html": "<p>dev-news는 개발과 AI 분야의 소식을 직접 챙겨 보려고 만든 사이트입니다. "
                 "모은 소식을 한국어로 정리해 하루 세 번(00시, 08시, 16시) 갱신하며, 출처는 "
                 + _esc(names) + "입니다. 모든 기사에 원문 링크를 함께 둡니다.</p>"},
        {"id": "method", "title": "수집 및 요약 방식",
         "html": "<p>수집, 요약, 게시는 자동으로 이루어집니다. 요약과 제목 번역은 AI가 작성하며, "
                 "기사마다 중요한 이유를 한 문장으로 덧붙입니다. 원문 본문을 가져오지 못한 경우에는 "
                 "해당 글에 달린 댓글을 바탕으로 요약하고, 그 사실을 표시합니다.</p>"},
        {"id": "criteria", "title": "기사 선별 기준",
         "html": "<p>하루 수백 건 중 회차당 20건을 게시합니다.</p>"
                 '<div class="crits">'
                 '<div class="crit"><span class="cnt">01</span><div><b>커뮤니티 반응</b><span>추천 수와 댓글 수</span></div></div>'
                 '<div class="crit"><span class="cnt">02</span><div><b>여러 출처에 함께 오른 기사</b><span>출처가 겹칠수록 앞에 둡니다</span></div></div>'
                 '<div class="crit"><span class="cnt">03</span><div><b>개발과의 관련성</b><span>소송, 정치, 연예 등 기술 외 사안은 제외</span></div></div>'
                 "</div>"},
        {"id": "support", "title": "후원 및 문의",
         "html": "<p>이 사이트가 도움이 되었다면 후원할 수 있습니다. 출처 추가·제외 요청, 오류 제보, "
                 "제안은 GitHub Issues로 보내 주세요.</p>"},
        {"id": "privacy", "title": "개인정보 처리",
         "html": "<p>이 사이트는 서버와 회원 기능이 없습니다. 보관함과 읽음 표시는 브라우저의 "
                 "localStorage에만 저장되며 외부로 전송되지 않습니다. 광고가 게재되는 경우 광고 사업자가 "
                 "쿠키 등을 통해 정보를 수집할 수 있으며, 해당 사항은 이 페이지에 명시합니다.</p>"},
    ]


_ICON = {
    "gh": '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.58 2 12.25c0 4.53 2.87 8.37 6.84 9.72.5.1.68-.22.68-.49 0-.24-.01-.88-.01-1.72-2.78.62-3.37-1.37-3.37-1.37-.45-1.18-1.11-1.5-1.11-1.5-.91-.63.07-.62.07-.62 1 .07 1.53 1.06 1.53 1.06.9 1.57 2.35 1.12 2.92.86.09-.67.35-1.12.63-1.38-2.22-.26-4.56-1.14-4.56-5.06 0-1.12.39-2.03 1.03-2.75-.1-.26-.45-1.3.1-2.7 0 0 .84-.28 2.75 1.05a9.4 9.4 0 015 0c1.91-1.33 2.75-1.05 2.75-1.05.55 1.4.2 2.44.1 2.7.64.72 1.03 1.63 1.03 2.75 0 3.93-2.34 4.8-4.57 5.05.36.32.68.94.68 1.9 0 1.38-.01 2.49-.01 2.83 0 .27.18.6.69.49A10.02 10.02 0 0022 12.25C22 6.58 17.52 2 12 2z"/></svg>',
    "ext": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 4h6v6M20 4l-9 9M18 13v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h6"/></svg>',
    "cup": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 8h12v6a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5V8zM16 9h2a2.5 2.5 0 0 1 0 5h-2M6 3v2M10 3v2M14 3v2"/></svg>',
    "issue": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/></svg>',
}

_STATIC_CSS = """
:root{--bg:#f4f4f6;--panel:#fff;--line:#e7e7ec;--line2:#f0f0f4;--tx:#1c1c22;--tx2:#54545f;--tx3:#8b8b98;--pri:#7c6ee6;--pri-bg:#efedfd;--pri-dk:#5b4fd0;
--shadow-card:0 0 0 1px rgba(25,28,33,.06),0 1px 1px -.5px rgba(0,0,0,.05),0 3px 3px -1.5px rgba(0,0,0,.04),0 6px 6px -3px rgba(0,0,0,.03)}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);font-family:"Pretendard Variable","Pretendard","Apple SD Gothic Neo","Noto Sans KR",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:16px;line-height:1.7;letter-spacing:-.008em;-webkit-font-smoothing:antialiased;word-break:keep-all;overflow-wrap:anywhere}
.page{max-width:1180px;margin:0 auto;padding:34px 34px 70px}
.top{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:22px;font-size:14px}
.top a{color:var(--tx2);text-decoration:none}.top a:hover{color:var(--pri-dk)}
h1{font-size:27px;font-weight:800;letter-spacing:-.035em;margin:0 0 6px;display:flex;align-items:center;gap:11px}
.hmark{width:26px;height:26px;flex:none;display:block}
.sub{font-size:15px;color:var(--tx3);margin-bottom:26px}
.about{display:grid;grid-template-columns:320px minmax(0,1fr);gap:24px;align-items:start}
.profile{background:var(--panel);border-radius:14px;box-shadow:var(--shadow-card);padding:30px 24px;display:flex;flex-direction:column;align-items:center;text-align:center;gap:12px}
.avatar{width:104px;height:104px;border-radius:50%;display:block}
.who b{font-size:21px;font-weight:800}.who p{font-size:14.5px;color:var(--tx2);margin:2px 0 0}
.pacts{display:flex;flex-direction:column;gap:8px;width:100%;margin-top:6px}.pacts .go{justify-content:center}
.doc{background:var(--panel);border-radius:14px;box-shadow:var(--shadow-card);padding:0 28px 6px}
section{padding:22px 0;border-bottom:1px solid var(--line2)}section:last-child{border-bottom:none}
h2{font-size:17px;font-weight:700;letter-spacing:-.01em;margin:0 0 8px}section.small h2{font-size:15px}
p{font-size:15px;line-height:1.75;color:var(--tx2);margin:0}section.small p{font-size:14px;color:var(--tx3)}
.go{display:inline-flex;align-items:center;gap:8px;background:var(--tx);color:#fff;text-decoration:none;font-size:15px;font-weight:700;padding:12px 20px;border-radius:10px;line-height:1.7}
.go.alt{background:none;color:var(--tx);box-shadow:inset 0 0 0 1.5px var(--line)}.go.coffee{background:#ffdd00;color:#1a1a1a}.go svg{width:18px;height:18px;flex:none}
.crits{display:flex;flex-direction:column;gap:12px;margin-top:12px}.crit{display:flex;gap:12px;align-items:flex-start}
.crit b{display:block;font-size:15px;font-weight:700}.crit span:last-child{font-size:14px;color:var(--tx3)}
.cnt{font-size:13px;font-weight:700;color:var(--pri-dk);background:var(--pri-bg);padding:3px 9px;border-radius:7px;line-height:1.5}
.acts{display:flex;flex-wrap:wrap;gap:10px;margin-top:14px}
.foot{margin-top:40px;padding-top:18px;border-top:1px solid var(--line);font-size:13.5px;color:var(--tx3);display:flex;gap:16px;flex-wrap:wrap}
.foot a{color:var(--tx3);text-decoration:none}.foot a:hover{color:var(--pri-dk)}
@media (max-width:900px){.page{padding:22px 16px 60px}.about{grid-template-columns:minmax(0,1fr);gap:12px}.avatar{width:88px;height:88px}.doc{padding:0 18px 4px}p{font-size:14px}}
"""

HMARK_SVG = ('<svg class="hmark" viewBox="0 0 32 32" aria-hidden="true">'
             '<rect width="32" height="32" rx="7.5" fill="#7c6ee6"/>'
             '<path d="M11.5 9.5 L20 16 L11.5 22.5" fill="none" stroke="#fff"'
             ' stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>')


def footer_html() -> str:
    """목록 아래와 정적 페이지 아래에 같은 링크 묶음. 크롤러가 소개·개인정보 페이지를
    찾는 길이다 — 레일 아이콘은 스크립트가 있어야 눌린다."""
    return ('<footer class="foot"><a href="/about/">소개</a><a href="/privacy/">개인정보 처리</a>'
            '<a href="https://github.com/dakcoe/dev-news" rel="noopener">GitHub 저장소</a>'
            '<span>© dev-news · 기사의 저작권은 각 원문 출처에 있습니다</span></footer>')


def _section_html(sec: dict, about: dict) -> str:
    inner = sec["html"]
    if sec["id"] == "support":
        repo = _safe_url(about.get("github") or "")
        coffee = _safe_url(about.get("coffee") or "")
        btns = ""
        if coffee:
            btns += (f'<a class="go coffee" href="{_esc(coffee)}" target="_blank" rel="noopener noreferrer">'
                     f'{_ICON["cup"]}{_esc(about.get("coffee_label") or "후원하기")}</a>')
        if repo:
            btns += (f'<a class="go alt" href="{_esc(repo)}/issues" target="_blank" rel="noopener noreferrer">'
                     f'{_ICON["issue"]}Issues 열기</a>')
        inner += f'<div class="acts">{btns}</div>'
    cls = ' class="small"' if sec["id"] == "privacy" else ""
    return f'<section id="{sec["id"]}"{cls}><h2>{_esc(sec["title"])}</h2>{inner}</section>'


def write_static_pages(out_dir: str, about: dict | None, enabled: dict | None) -> None:
    """/about/ 와 /privacy/ 를 정적 페이지로 둔다.

    앱 안의 소개 화면은 스크립트가 그려서 크롤러와 광고 심사 봇에게는 빈
    화면이다. 같은 글을 정적 HTML 로도 내보내 두면 소개·개인정보 처리 방침을
    링크 하나로 찾을 수 있다. 글은 about_copy() 한 곳에서 온다.
    """
    about = about or {}
    secs = about_copy(enabled)
    author = _esc(about.get("author") or "")
    author_url = _safe_url(about.get("author_url") or "")
    repo = _safe_url(about.get("github") or "")
    avatar = author_url.rstrip("/") + ".png?size=208" if author_url else ""
    bio = _esc(about.get("bio") or "")

    def page(title: str, desc: str, path: str, body: str) -> str:
        return ("<!DOCTYPE html>\n<html lang=\"ko\"><head><meta charset=\"utf-8\">"
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                f"<title>{_esc(title)} — dev-news</title>"
                f'<meta name="description" content="{_esc(desc)}">'
                f'<link rel="canonical" href="{site_url()}{path}">'
                '<link rel="icon" href="/favicon.svg" type="image/svg+xml">'
                f"<style>{_STATIC_CSS}</style></head><body><div class=\"page\">"
                '<div class="top"><a href="/">← dev-news</a></div>'
                + body + footer_html() + "</div></body></html>\n")

    profile = ('<div class="profile">'
               + (f'<img class="avatar" src="{_esc(avatar)}" alt="">' if avatar else "")
               + f'<div class="who"><b>{author}</b>' + (f"<p>{bio}</p>" if bio else "") + "</div>"
               + '<div class="pacts">'
               + (f'<a class="go" href="{_esc(author_url)}" target="_blank" rel="noopener noreferrer">{_ICON["gh"]}GitHub 프로필</a>' if author_url else "")
               + (f'<a class="go alt" href="{_esc(repo)}" target="_blank" rel="noopener noreferrer">저장소 {_ICON["ext"]}</a>' if repo else "")
               + "</div></div>")
    about_body = (f"<h1>{HMARK_SVG}<span>소개</span></h1><div class=\"sub\">만든 사람과 운영 방식</div>"
                  '<div class="about">' + profile + '<div class="doc">'
                  + "".join(_section_html(x, about) for x in secs) + "</div></div>")
    privacy_body = (f"<h1>{HMARK_SVG}<span>개인정보 처리</span></h1><div class=\"sub\">dev-news 가 다루는 정보</div>"
                    '<div class="doc" style="max-width:760px">'
                    + "".join(_section_html(x, about) for x in secs if x["id"] == "privacy")
                    + '<section><p><a href="/about/">사이트 소개 전체 보기 →</a></p></section></div>')
    for path, title, desc, body in (
        ("/about/", "소개", "dev-news 를 만든 사람, 수집·요약 방식, 기사 선별 기준, 후원 및 문의.", about_body),
        ("/privacy/", "개인정보 처리", "dev-news 는 서버와 회원 기능이 없으며 보관함·읽음 표시는 브라우저에만 저장됩니다.", privacy_body),
    ):
        d = os.path.join(out_dir, path.strip("/"))
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
            f.write(page(title, desc, path, body))


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
            f'<h2 class="rt"><a href="{_esc(_safe_url(d.get("url") or ""))}" rel="noopener">'
            f'{_esc(d.get("title") or "")}</a></h2>'
            '<div class="rm">' + "".join(meta) + "</div>"
            + (f'<div class="snip">{_esc(d["snip"])}</div>' if d.get("snip") else "")
            # 우리가 쓴 문장. 스크립트 없이도 보여야 "요약만 모아둔 곳"으로 안 읽힌다.
            + (f'<div class="rwhy"><b>중요한 이유</b>{_esc(d["why"])}</div>' if d.get("why") else "")
            + "</div><div></div><div></div></div>")
    return (
        # ⚠️ 제목 마크는 JS가 그리는 것과 같은 마크업이어야 한다.
        # 다르면 스크립트가 뜨는 순간 제목 줄이 흔들린다.
        '<h1><svg class="hmark" viewBox="0 0 32 32" aria-hidden="true">'
        '<rect width="32" height="32" rx="7.5" fill="#7c6ee6"/>'
        '<path d="M11.5 9.5 L20 16 L11.5 22.5" fill="none" stroke="#fff"'
        ' stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>'
        "</svg><span>오늘의 뉴스</span></h1>"
        '<div class="sub">매일 00시·08시·16시에 수집합니다. '
        "30일 지난 기사는 검색으로 찾을 수 있습니다 "
        f"(최근 {batches}회차) · 하루 수백 건 중 회차당 20건을 고릅니다</div>"
        '<div class="status"><div class="stmeta">'
        f'<b>최근 30일 {len(view_model)}건</b> · 수집 {collected.strftime("%Y년 %m월 %d일")}<br>'
        f'<span class="l2">회차 {batches}개 · 해커뉴스·GitHub 트렌딩·Lobsters·'
        "dev.to·긱뉴스에서 모읍니다</span></div></div>"
        # 검색·필터 바 자리. 높이를 잡아두지 않으면 스크립트가 뜰 때 목록이 밀린다.
        '<div class="bar"><div class="search">'
        '<input placeholder="검색 (아카이브 포함)…" disabled></div></div>'
        '<div class="layout"><div class="facet" style="min-height:420px"></div>'
        '<div class="feed">' + "".join(rows) + "</div></div>"
        + footer_html())


# 검색 결과에 뜨는 한 줄. 네이버 서치어드바이저가 80자 이내를 요구한다.
# 한때 오늘 실린 기사 제목을 붙여 매일 달라지게 했는데, 남의 기사 제목이
# 사이트 설명 자리를 차지해 이 사이트가 무엇인지 알 수 없게 됐다. 설명은
# 사이트를 설명해야 한다.
META_DESC = ("해커뉴스·GitHub 트렌딩·Lobsters·dev.to·긱뉴스의 개발·AI 소식을 "
             "매일 세 번 한국어로 요약합니다.")


def _meta_desc(view_model: list[dict]) -> str:
    return _esc(META_DESC)


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
            + _json_for_script(data)
            + "</script>")


# 이름을 적어 두는 크롤러들. `User-agent: *`가 이미 전체를 허용하지만,
# 이 봇들은 "이름이 안 적혀 있으면 안 긁는다"는 정책을 쓰거나(Google-Extended,
# Applebot-Extended) 운영자가 막았는지를 이름 단위로 확인한다. 명시해 두면
# AI 답변의 출처로 인용될 길이 열린다 — 이게 GEO의 기술적 절반이다.
AI_AGENTS = [
    # ⚠️ 광고 크롤러를 맨 앞에 둔다. 애드센스 크롤러는 `User-agent: *` 무리를
    # 무시하므로 이름이 없으면 자기에게 적용할 규칙이 없다고 본다. robots.txt가
    # 아예 없던 2026-09-07에는 ads.txt가 확인됐는데, 08일에 이 파일을 만들면서
    # 광고 쪽 이름을 빠뜨리자 "ads.txt를 찾을 수 없음"으로 바뀌었다.
    "Mediapartners-Google",        # 애드센스 콘텐츠 크롤러
    "AdsBot-Google",               # ads.txt·방문 페이지 확인
    "AdsBot-Google-Mobile",
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
                f'  <url><loc>{base}/about/</loc><changefreq>monthly</changefreq></url>\n'
                f'  <url><loc>{base}/privacy/</loc><changefreq>monthly</changefreq></url>\n'
                '</urlset>\n')


def render(articles: list[dict], out_path: str, collected: datetime | None = None,
           enabled: dict[str, bool] | None = None, ads: dict | None = None,
           about: dict | None = None) -> str:
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
            .replace("__DATA_JSON__", _json_for_script(view_model))
            .replace("__SRC_JSON__", _json_for_script(sources))
            .replace("__TAG_JSON__", _json_for_script(
                {tid: {"label": spec["label"], "group": spec["group"]}
                 for tid, spec in tag_vocab.VOCAB.items()}))
            .replace("__COLLECTED_LABEL__", collected.strftime("%p %I:%M").replace("AM", "오전").replace("PM", "오후"))
            .replace("__COLLECTED__", collected.isoformat())
            .replace("__DATE__", collected.strftime("%Y-%m-%d"))
            .replace("__SEO_HTML__", _seo_html(view_model, collected))
            .replace("__JSONLD__", _jsonld(view_model, collected))
            .replace("__META_DESC__", _meta_desc(view_model))
            .replace("__SITE_URL__", site_url())
            .replace("__ADS_HEAD__", _ads_head(ads_cfg))
            .replace("__ADS_JSON__", _json_for_script(ads_cfg))
            .replace("__ABOUT_JSON__", _json_for_script({**(about or {}), "copy": about_copy(enabled)})))
    write_static_pages(os.path.dirname(os.path.abspath(out_path)), about, enabled)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[render] {out_path} · 기사 {len(articles)}건")
    return out_path
