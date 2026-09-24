"""학습 노트 (/learn/) — 강의 영상 대본을 옮긴 글을 정적 페이지로 낸다.

뉴스 목록은 전부 자동 요약이라 애드센스가 '가치가 별로 없는 콘텐츠'로 거절했다
(2026-09-25). 직접 쓴 해설이 사이트 안에 있어야 한다. 뉴스 화면에는 섞지 않고,
푸터 링크 한 줄과 사이트맵으로만 잇는다.

원고는 learn/articles/<slug>.html 이다. 첫 줄 `<!--META {json} -->` 에 제목·분류·
순서·요약·날짜를 적고, 그 아래는 본문 조각(h2 id="sN" 로 절을 나눈다)이다.
여기서 공통 틀을 씌워 docs/learn/<slug>/index.html 과 목록 docs/learn/index.html 을 만든다.
"""
from __future__ import annotations

import glob
import html
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "learn", "articles")
CATS = ["머신러닝", "딥러닝", "컴퓨터구조", "운영체제"]   # 목록에 나오는 순서
CAT_ID = {"머신러닝": "ml", "딥러닝": "dl", "컴퓨터구조": "ca", "운영체제": "os"}
AUTHOR = "suhyun"

CSS = """:root{--bg:#f4f4f6;--panel:#fff;--line:#e7e7ec;--tx:#1c1c22;--tx2:#54545f;--tx3:#8b8b98;--pri:#7c6ee6;--pri-bg:#efedfd;--pri-dk:#5b4fd0;
--shadow-card:0 0 0 1px rgba(25,28,33,.06),0 1px 1px -.5px rgba(0,0,0,.05),0 3px 3px -1.5px rgba(0,0,0,.04),0 6px 6px -3px rgba(0,0,0,.03)}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);font-family:"Pretendard Variable","Pretendard","Apple SD Gothic Neo","Noto Sans KR",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:16px;line-height:1.7;word-break:keep-all;overflow-wrap:anywhere;-webkit-font-smoothing:antialiased}
a{color:inherit}
.page{max-width:1080px;margin:0 auto;padding:34px 34px 70px}
.crumb{font-size:14px;color:var(--tx3);margin-bottom:22px;display:flex;gap:8px;flex-wrap:wrap}
.crumb a{color:var(--tx2);text-decoration:none}.crumb a:hover{color:var(--pri-dk)}
.grid{display:grid;grid-template-columns:minmax(0,1fr) 240px;gap:24px;align-items:start}
article,.list{background:var(--panel);border-radius:14px;box-shadow:var(--shadow-card);padding:36px 44px 40px}
.kicker{font-size:13.5px;font-weight:700;color:var(--pri-dk)}
h1{font-size:30px;font-weight:800;letter-spacing:-.04em;line-height:1.3;margin:6px 0 10px}
.meta{font-size:13.5px;color:var(--tx3);display:flex;gap:10px;flex-wrap:wrap}
.lead{margin:26px 0 8px;background:var(--pri-bg);border-radius:12px;padding:16px 20px;font-size:15.5px;line-height:1.75;color:#3d3480}
.lead b{color:var(--pri-dk)}
h2{font-size:20px;font-weight:800;letter-spacing:-.025em;margin:38px 0 12px;scroll-margin-top:20px}
h3{font-size:16px;font-weight:700;margin:22px 0 6px}
p{font-size:16px;line-height:1.85;color:#3a3a44;margin:0}
p+p{margin-top:14px}
ol,ul{font-size:16px;line-height:1.85;color:#3a3a44;margin:10px 0 0;padding-left:22px}
li+li{margin-top:4px}
code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.9em;background:#f4f4f6;border-radius:5px;padding:1px 5px}
pre{background:#f4f4f6;border-radius:10px;padding:14px 16px;overflow-x:auto;font-size:14px;line-height:1.6;margin:14px 0}
pre code{background:none;padding:0}
.tw{overflow-x:auto;margin:16px 0 4px}
table{width:100%;border-collapse:collapse;font-size:14.5px}
th,td{border:1px solid var(--line);padding:10px 12px;text-align:left;vertical-align:top;overflow-wrap:normal}
th{white-space:nowrap}
th{background:#fafafb;font-weight:700}
.note{font-size:14px;color:var(--tx3);margin-top:8px}
.toc{position:sticky;top:20px;background:var(--panel);border-radius:14px;box-shadow:var(--shadow-card);padding:18px 18px 16px}
.toc b{font-size:13px;color:var(--tx3);display:block;margin-bottom:8px}
.toc ol{font-size:13.5px;line-height:1.6;padding-left:18px;margin:0;color:var(--tx2)}
.toc a{text-decoration:none}.toc a:hover{color:var(--pri-dk)}
.next{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:40px}
.next a{display:block;border-radius:12px;box-shadow:inset 0 0 0 1.5px var(--line);padding:14px 16px;text-decoration:none}
.next a:hover{box-shadow:inset 0 0 0 1.5px var(--pri)}
.next small{display:block;font-size:12.5px;color:var(--tx3)}
.next span{font-size:15px;font-weight:700}
.next .r{text-align:right;grid-column:2}
.list h2{margin-top:30px}.list h2:first-of-type{margin-top:18px}
.item{display:block;text-decoration:none;padding:14px 0;border-top:1px solid #f0f0f4}
.item b{display:block;font-size:16px}.item b:hover{color:var(--pri-dk)}
.item span{display:block;font-size:14px;color:var(--tx3);margin-top:2px}
.foot{margin-top:40px;padding-top:18px;border-top:1px solid var(--line);font-size:13.5px;color:var(--tx3);display:flex;gap:16px;flex-wrap:wrap}
.foot a{text-decoration:none}.foot a:hover{color:var(--pri-dk)}
@media (max-width:900px){
  .page{padding:18px 14px 50px}
  .grid{grid-template-columns:minmax(0,1fr)}
  .toc{position:static;order:-1}
  article,.list{padding:24px 20px 28px}
  h1{font-size:24px}
  p,ol,ul{font-size:15.5px}
  .next{grid-template-columns:1fr}.next .r{grid-column:auto}
}"""

FOOT = ('<div class="foot"><a href="/">dev-news</a><a href="/learn/">학습 노트</a>'
        '<a href="/about/">소개</a><a href="/privacy/">개인정보 처리</a></div>')
E = html.escape


def _page(title: str, desc: str, path: str, base: str, body: str) -> str:
    return (f'<!DOCTYPE html>\n<html lang="ko"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{E(title)}</title><meta name="description" content="{E(desc)}">'
            f'<link rel="canonical" href="{base}{path}"><link rel="icon" href="/favicon.svg" type="image/svg+xml">'
            f'<meta property="og:title" content="{E(title)}"><meta property="og:description" content="{E(desc)}">'
            f'<meta property="og:image" content="{base}/og.png">'
            '<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.css">'
            f'<style>{CSS}</style></head><body><div class="page">\n{body}\n{FOOT}\n</div></body></html>\n')


def load(src: str = SRC) -> list[dict]:
    out = []
    for path in sorted(glob.glob(os.path.join(src, "*.html"))):
        text = open(path, encoding="utf-8").read()
        m = re.match(r"<!--META (\{.*?\}) -->\n", text, re.S)
        if not m:
            print(f"[learn] META 없음 — 건너뜀: {os.path.basename(path)}")
            continue
        meta = json.loads(m.group(1))
        meta["body"] = text[m.end():]
        meta["toc"] = re.findall(r'<h2 id="(s\d+)">(.*?)</h2>', meta["body"])
        out.append(meta)
    return sorted(out, key=lambda a: (CATS.index(a["cat"]) if a["cat"] in CATS else 99, a["order"]))


def _minutes(body: str) -> int:
    # 한국어 본문은 분당 500자 안팎으로 읽는다
    return max(1, round(len(re.sub(r"<[^>]+>", "", body)) / 500))


def _article(a: dict, prev: dict | None, nxt: dict | None, base: str) -> str:
    cat = E(a["cat"])
    toc = "".join(f'<li><a href="#{i}">{re.sub(r"^\d+\.\s*", "", t)}</a></li>' for i, t in a["toc"])
    body = re.sub(r"(<table>.*?</table>)", r'<div class="tw">\1</div>', a["body"], flags=re.S)
    links = ""
    if prev:
        links += f'<a href="/learn/{prev["slug"]}/"><small>← 이전 글</small><span>{E(prev["title"])}</span></a>'
    if nxt:
        links += f'<a class="r" href="/learn/{nxt["slug"]}/"><small>다음 글 →</small><span>{E(nxt["title"])}</span></a>'
    y, mo, d = a["date"].split("-")
    html_body = (
        f'<nav class="crumb"><a href="/">dev-news</a><span>›</span><a href="/learn/">학습 노트</a>'
        f'<span>›</span><a href="/learn/#{CAT_ID.get(a["cat"], "etc")}">{cat}</a></nav>\n'
        f'<div class="grid"><article>\n<div class="kicker">{cat} {a["order"]}편</div>\n'
        f'<h1>{E(a["title"])}</h1>\n'
        f'<div class="meta"><span>{AUTHOR}</span><span>·</span><span>{int(y)}년 {int(mo)}월 {int(d)}일</span>'
        f'<span>·</span><span>읽는 데 약 {_minutes(a["body"])}분</span></div>\n'
        f'<div class="lead"><b>한 줄로:</b> {E(a["lead"])}</div>\n{body}'
        f'<div class="next">{links}</div>\n</article>\n'
        f'<aside class="toc"><b>목차</b><ol>{toc}</ol></aside></div>')
    return _page(f'{a["title"]} · 학습 노트 · dev-news', a["desc"], f'/learn/{a["slug"]}/', base, html_body)


def _index(arts: list[dict], base: str) -> str:
    parts = ['<nav class="crumb"><a href="/">dev-news</a><span>›</span><span>학습 노트</span></nav>',
             '<div class="list"><h1>학습 노트</h1>',
             '<p>대학 전공 과목을 공부하며 만든 강의 영상의 대본을 글로 옮겼습니다. '
             '처음 보는 사람도 따라올 수 있게 개념 하나씩 풀어 씁니다.</p>']
    for cat in CATS:
        items = [a for a in arts if a["cat"] == cat]
        if not items:
            continue
        parts.append(f'<h2 id="{CAT_ID[cat]}">{E(cat)}</h2>')
        parts += [f'<a class="item" href="/learn/{a["slug"]}/"><b>{a["order"]}. {E(a["title"])}</b>'
                  f'<span>{E(a["desc"])}</span></a>' for a in items]
    parts.append('</div>')
    return _page("학습 노트 · dev-news", "머신러닝·딥러닝·컴퓨터구조·운영체제 강의 영상 대본을 옮긴 해설 글.",
                 "/learn/", base, "\n".join(parts))


def build(docs_dir: str, base: str, src: str = SRC) -> list[str]:
    """페이지를 쓰고 사이트맵에 넣을 경로 목록을 돌려준다. 원고가 없으면 빈 목록."""
    arts = load(src)
    if not arts:
        return []
    out = os.path.join(docs_dir, "learn")
    os.makedirs(out, exist_ok=True)
    for a in arts:
        same = [b for b in arts if b["cat"] == a["cat"]]
        i = same.index(a)
        page = _article(a, same[i - 1] if i else None, same[i + 1] if i + 1 < len(same) else None, base)
        os.makedirs(os.path.join(out, a["slug"]), exist_ok=True)
        with open(os.path.join(out, a["slug"], "index.html"), "w", encoding="utf-8") as f:
            f.write(page)
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as f:
        f.write(_index(arts, base))
    print(f"[learn] 학습 노트 {len(arts)}편")
    return ["/learn/"] + [f'/learn/{a["slug"]}/' for a in arts]
