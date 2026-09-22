"""같은 사건을 다룬 기사 거르기 (same-story).

주소·제목 비교(dedup.py)로는 못 잡는 중복이 남는다 — 서로 다른 매체가 같은
발표를 다르게 쓴 글("Grok 4.7" ⇄ "xAI launches Grok 4.7 at bargain prices…"),
한 쪽 제목이 두 단어뿐인 글. 2026-09 게재분에서 이런 쌍이 회차당 2~3개였다.

두 단계다.
  1. bge-m3 임베딩 코사인 유사도로 후보를 추린다 (제목·원제·요약 앞부분).
     ≥ AUTO 는 판정 없이 같은 기사로 본다.
  2. JUDGE ~ AUTO 구간만 Groq 의 qwen 에게 "같음/다름" 을 묻는다.

기준값과 판정 프롬프트는 9월 69회차를 재현해 정했다 — 13만 쌍 중 JUDGE 이상
425쌍, AUTO 이상은 68쌍 중 67쌍이 실제로 같은 기사였고, 판정은 150쌍 표본에서
오탐 0 · 재현율 0.77 이었다. 같은 주제의 다른 소식("GPT-6 출시" ⇄ "GPT-6
벤치마크 의견")을 묶는 쪽이 더 나쁘다고 보고 오탐을 줄이는 쪽으로 맞췄다
(gpt-oss-120b 는 이런 쌍을 묶어서 정밀도 0.63 이었다).

임베딩 모델은 이 단계에서만 올리고 끝나면 내린다 (약 2GB).
실패하면 아무것도 빼지 않는다. 여기서 빠진 기사는 seen 에 넣는다 (build.py).
"""
from __future__ import annotations

import gc
from datetime import timedelta

EMBED_MODEL = "BAAI/bge-m3"
JUDGE_MODEL = "qwen/qwen3.8-27b"   # Groq
AUTO = 0.85
JUDGE = 0.65
WINDOW_HOURS = 48
# 기사 하나에 판정을 몇 번까지 묻나. 큰 발표가 있는 날은 비슷한 글이 열 건 넘게
# 몰려서, 제한이 없으면 한 기사에 판정이 줄줄이 붙는다. 유사도 높은 순으로 묻는다.
MAX_JUDGE_PER_ARTICLE = 3

PROMPT = """두 기사가 같은 사건을 다루는지 판정해라. 독자에게 둘 다 보여주면 같은 소식을 두 번 읽는 셈인지가 기준이다.

같음:
- 같은 글·같은 발표·같은 출시·같은 사고를 다룬다. 출처·언어·관점이 달라도 같다.
- 제목이 번역 차이만 있고 같은 글을 가리키면 같음이다. 요약에 적힌 세부가 달라도 마찬가지다.
- 저장소와 그 저장소를 소개하는 글(Show HN 등)은 같음이다.

다름:
- 같은 회사·제품이라도 다른 사건이다. 예: 출시 발표 vs 가격 인하, 출시 발표 vs 그 제품의 개발자 문서·벤치마크·체험기·의견 글, 서로 다른 복제 프로젝트.
- 며칠 뒤 새로운 사실이 더해진 후속 보도.
- 주제만 비슷한 글.

"같음" 또는 "다름" 한 단어로만 답해라.

[기사 A]
제목: {ta}
요약: {sa}

[기사 B]
제목: {tb}
요약: {sb}"""


def _title(a: dict) -> str:
    ko, orig = a.get("ko_title") or "", a.get("title") or ""
    return f"{ko} / {orig}" if ko and ko != orig else (ko or orig)


def _text(a: dict) -> str:
    return f"{_title(a)}. {(a.get('summary') or '')[:200]}"


def _embed(texts: list[str]):
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(EMBED_MODEL)
    try:
        return model.encode(texts, batch_size=32, normalize_embeddings=True,
                            show_progress_bar=False).tolist()
    finally:
        del model
        _free()


def _dot(u, v) -> float:
    # 정규화된 벡터라 내적이 곧 코사인이다. numpy 에 기대지 않아 테스트가 가볍다.
    return float(sum(x * y for x, y in zip(u, v)))


def _free() -> None:
    gc.collect()
    try:
        import torch
        if torch.backends.mps.is_available():
            torch.mps.empty_cache()
    except Exception:
        pass


class _Judge:
    """Groq qwen 에게 묻는다. 로컬 27B 는 쌍마다 7초가 걸려 회차가 늘어졌다."""

    def same(self, a: dict, b: dict) -> bool:
        import os
        import re
        import time
        from news.summarizer import ENDPOINTS, RateLimited, _call_openai_compatible
        msg = PROMPT.format(ta=_title(a), sa=(a.get("summary") or "")[:300],
                            tb=_title(b), sb=(b.get("summary") or "")[:300])
        for attempt in range(2):
            try:
                out = _call_openai_compatible(msg, JUDGE_MODEL, os.environ["GROQ_API_KEY"],
                                              ENDPOINTS["groq"])
                # 추론이 토큰 상한에 걸려 닫히지 않은 <think> 는 끝까지 지운다. 추론
                # 안에서 프롬프트의 "같음" 을 인용하므로 그대로 두면 오탐이 난다.
                ans = re.sub(r"<think>.*?(</think>|$)", "", out, flags=re.S).strip()
                return ans.startswith("같음")
            except RateLimited as e:
                # 분당 토큰 한도를 '왜 중요한가'와 나눠 쓴다. 한 번만 기다린다.
                if attempt or e.wait > 60:
                    raise
                time.sleep(e.wait + 1)
        return False

    def close(self) -> None:
        pass


def recent_published(archive_articles: list[dict], now, hours: int = WINDOW_HOURS) -> list[dict]:
    from datetime import datetime
    cutoff = now - timedelta(hours=hours)
    out = []
    for a in archive_articles:
        try:
            if datetime.fromisoformat(a.get("batch") or "") >= cutoff:
                out.append(a)
        except ValueError:
            continue
    return out


def drop_same_story(new: list[dict], recent: list[dict], judge=None, embed=None
                    ) -> tuple[list[dict], list[dict]]:
    """새 기사 중 최근 게재분이나 같은 회차의 앞선 기사와 같은 사건인 것을 뺀다.

    new 는 선별 순서(위가 우선)다. 같은 회차 안에서 겹치면 뒤의 것을 뺀다.
    반환: (남길 것, 뺀 것). 뺀 기사에는 same_as(겹친 기사 주소)를 붙인다.
    """
    if not new:
        return new, []
    own_judge = judge is None
    judge = judge or _Judge()
    embed = embed or _embed
    try:
        vecs = embed([_text(a) for a in recent + new])
        old_vecs, new_vecs = vecs[:len(recent)], vecs[len(recent):]
        kept_idx: list[int] = []
        kept, dropped = [], []
        judged, judge_off = 0, False
        for i, a in enumerate(new):
            others = [(recent[j], _dot(old_vecs[j], new_vecs[i])) for j in range(len(recent))]
            others += [(new[k], _dot(new_vecs[k], new_vecs[i])) for k in kept_idx]
            hit, asked = None, 0
            for b, sim in sorted(others, key=lambda x: -x[1]):
                if sim < JUDGE or asked >= MAX_JUDGE_PER_ARTICLE:
                    break
                if sim >= AUTO:
                    hit = (b, sim, "유사도")
                    break
                if judge_off:
                    break
                asked += 1
                judged += 1
                try:
                    same = judge.same(a, b)
                except Exception as e:
                    # 판정기가 안 뜨면 이 회차는 유사도로만 거른다
                    print(f"[같은 사건] 판정 모델 실패 ({type(e).__name__}: {e}) — 유사도 {AUTO} 이상만 거른다")
                    judge_off = True
                    break
                if same:
                    hit = (b, sim, "판정")
                    break
            if hit:
                b, sim, why = hit
                print(f"[같은 사건] {why} {sim:.2f} · {_title(a)[:40]} ⇄ {_title(b)[:40]}")
                dropped.append({**a, "same_as": b.get("url")})
            else:
                kept_idx.append(i)
                kept.append(a)
        print(f"[같은 사건] 새 기사 {len(new)}건 · 판정 {judged}쌍 · 제외 {len(dropped)}건")
        return kept, dropped
    except Exception as e:
        print(f"[같은 사건] 건너뜀 ({type(e).__name__}: {e}) — 이번 회차는 거르지 않는다")
        return new, []
    finally:
        if own_judge:
            judge.close()
