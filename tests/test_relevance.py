"""LLM 분류 게이트 (llm-relevance-gate).

차단 목록으로는 못 잡는 비개발 기사를 요약 호출에 필드를 하나 더 받아 거른다.
키워드로는 원리적으로 판별할 수 없는 것들이다 — 전부 AI가 소재라 개발 키워드에
걸리고 차단어도 없다:

  소니·워너 Anthropic 저작권 소송 / 호주 부당해고 AI 조언 판결
  보코니대 학점 실험 / 영국 일자리 시장 분화

fail-open 원칙: 분류가 없거나 이상하면 게재한다. 이 필드가 깨졌을 때
페이지가 비는 것이 훨씬 나쁘다.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from news.summarizer import PROMPT, _parse  # noqa: E402
from news.core.filters import drop_irrelevant  # noqa: E402


def _reply(relevance=None, title="제목", summary="요약문", why="이유"):
    lines = [f"번역제목: {title}", f"요약: {summary}", f"왜중요: {why}"]
    if relevance is not None:
        lines.append(f"분류: {relevance}")
    return "\n".join(lines)


# --------------------------------------------------------------- 파싱
def test_parses_relevance():
    for value, expected in (("게재", "게재"), ("제외", "제외")):
        assert _parse(_reply(value))["relevance"] == expected


def test_relevance_tolerates_decoration():
    """모델이 괄호·설명을 덧붙이는 경우."""
    for value in ("제외 (기술 밖 사건)", "**제외**", "제외."):
        assert _parse(_reply(value))["relevance"] == "제외"


def test_missing_relevance_defaults_to_publish():
    """필드가 없으면 게재 쪽으로 — fail-open."""
    assert _parse(_reply(None))["relevance"] == "게재"


def test_unknown_relevance_value_defaults_to_publish():
    for value in ("", "잡담", "irrelevant", "??"):
        assert _parse(_reply(value))["relevance"] == "게재"


def test_relevance_does_not_leak_into_other_fields():
    parsed = _parse(_reply("제외"))
    for field in ("summary", "why", "ko_title"):
        assert "제외" not in (parsed[field] or "")


# --------------------------------------------------------------- 프롬프트
def test_prompt_asks_for_relevance():
    assert "분류:" in PROMPT
    for value in ("게재", "제외"):
        assert value in PROMPT


# --------------------------------------------------------------- 게재 제외
def _art(relevance, url="https://e.com/x", llm_done=True):
    return {"url": url, "title": "t", "relevance": relevance, "llm_done": llm_done}


def test_drops_only_irrelevant():
    kept, dropped = drop_irrelevant([
        _art("게재", "https://e.com/1"),
        _art("게재", "https://e.com/2"),
        _art("제외", "https://e.com/3"),
    ])
    assert [a["url"] for a in kept] == ["https://e.com/1", "https://e.com/2"]
    assert [a["url"] for a in dropped] == ["https://e.com/3"]


def test_keeps_articles_without_relevance():
    kept, dropped = drop_irrelevant([{"url": "https://e.com/1", "llm_done": True}])
    assert len(kept) == 1 and not dropped


def test_unsummarized_articles_are_not_dropped():
    """요약을 못 받은 기사는 분류도 없다 — 여기서 빼면 안 된다(다음 회차 재시도)."""
    kept, dropped = drop_irrelevant([_art(None, "https://e.com/1", llm_done=False)])
    assert len(kept) == 1 and not dropped


def test_empty_input():
    assert drop_irrelevant([]) == ([], [])


# --------------------------------------------------------------- 조기 중단
# 여유분(overpick)을 다 요약하면 무관이 없는 회차에도 호출이 늘어난다.
# 게재 가능분이 목표에 닿는 즉시 멈춰야 한다.
def _fake_summarize(monkeypatch, relevances):
    """_call을 가로채 정해진 분류를 순서대로 돌려준다. 호출 수를 센다."""
    import news.summarizer as S
    calls = {"n": 0}

    def fake_call(prompt, provider, model, api_key):
        i = calls["n"]
        calls["n"] += 1
        rel = relevances[i] if i < len(relevances) else "개발"
        return f"번역제목: 제목{i}\n요약: 요약{i}\n왜중요: 이유{i}\n분류: {rel}"

    monkeypatch.setattr(S, "_call", fake_call)
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    return S, calls


def test_stops_once_target_reached(monkeypatch):
    S, calls = _fake_summarize(monkeypatch, ["게재"] * 10)
    arts = [{"title": f"t{i}", "url": f"https://e.com/{i}"} for i in range(10)]
    out = S.summarize_all(arts, provider="groq", pause=0, stop_after=3)
    assert calls["n"] == 3, "목표를 채우면 더 부르면 안 된다"
    assert sum(1 for a in out if a.get("llm_done")) == 3
    assert len(out) == 10, "부르지 않은 기사도 목록에는 남아야 한다"


def test_irrelevant_does_not_count_toward_target(monkeypatch):
    S, calls = _fake_summarize(monkeypatch, ["제외", "제외", "게재", "게재", "게재"])
    arts = [{"title": f"t{i}", "url": f"https://e.com/{i}"} for i in range(6)]
    S.summarize_all(arts, provider="groq", pause=0, stop_after=3)
    assert calls["n"] == 5, "제외 2건만큼 더 불러야 한다"


def test_no_stop_after_summarizes_everything(monkeypatch):
    S, calls = _fake_summarize(monkeypatch, ["게재"] * 4)
    arts = [{"title": f"t{i}", "url": f"https://e.com/{i}"} for i in range(4)]
    S.summarize_all(arts, provider="groq", pause=0)
    assert calls["n"] == 4


def test_skipped_articles_are_not_published(monkeypatch):
    """부르지 않은 기사는 llm_done=False라 게시·seen 등록에서 빠진다."""
    S, _ = _fake_summarize(monkeypatch, ["게재"] * 5)
    arts = [{"title": f"t{i}", "url": f"https://e.com/{i}"} for i in range(5)]
    out = S.summarize_all(arts, provider="groq", pause=0, stop_after=2)
    assert [a.get("llm_done", False) for a in out] == [True, True, False, False, False]


# --------------------------------------------------------------- 기본 꺼짐
def test_gate_is_off_by_default():
    """무료 gpt-oss-120b의 판정이 아직 안정적이지 않다 — 켜는 것은 사용자 결정."""
    import yaml
    with open(os.path.join(ROOT, "config.yaml"), encoding="utf-8") as f:
        sc = yaml.safe_load(f)["scraper"]
    assert sc.get("relevance_gate") is False
