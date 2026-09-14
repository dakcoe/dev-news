"""주 모델이 한도(429)에 걸렸을 때 예비 모델로 갈아탄다.

고치기 전에는 한 모델이 한도에 걸리면 그 회차의 남은 기사가 통째로 미게시됐다.
2026-09-14 회차 로그가 그 모습이다.

    · 한도(429) — 6초 대기 후 재시도 2/2
    [한도] 요약 15/19건 완료 후 한도 도달 — 나머지 4건은 이번 회차 미게시

Groq의 무료 한도는 모델별로 따로 세므로, 다른 모델로 갈아타면 예산이 새로 생긴다.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from news import summarizer as S  # noqa: E402

ARTICLES = [{"title": f"제목 {i}", "url": f"https://e.com/{i}",
             "source": "hackernews", "content": "본문입니다. " * 20}
            for i in range(4)]


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_WHY_MODEL", raising=False)
    monkeypatch.delenv("LLM_FALLBACK_MODELS", raising=False)


def stub_calls(monkeypatch, limited: set[str]):
    """limited에 든 모델은 항상 429를 내고, 나머지는 정상 요약을 돌려준다.

    호출된 모델 이름을 순서대로 모아 반환한다.
    """
    seen = []

    def fake_call(prompt, provider, model, api_key):
        seen.append(model)
        if model in limited:
            raise S.RateLimited(3)
        return "번역제목: 한국어 제목\n요약: 요약 문장이다.\n왜중요: 중요한 이유다."

    monkeypatch.setattr(S, "_call", fake_call)
    monkeypatch.setattr(S.time, "sleep", lambda *a: None)
    return seen


def test_주_모델이_막히면_예비_모델로_갈아탄다(monkeypatch):
    seen = stub_calls(monkeypatch, limited={"openai/gpt-oss-120b"})
    out = S.summarize_all(ARTICLES, model="openai/gpt-oss-120b", pause=0,
                          max_calls=50, fallback_models=["예비-1"])
    assert all(a["llm_done"] for a in out), "한 건도 빠지면 안 된다"
    assert "예비-1" in seen


def test_예비_모델도_막히면_다음_예비로_간다(monkeypatch):
    seen = stub_calls(monkeypatch, limited={"주-모델", "예비-1"})
    out = S.summarize_all(ARTICLES, model="주-모델", pause=0, max_calls=50,
                          fallback_models=["예비-1", "예비-2"])
    assert all(a["llm_done"] for a in out)
    assert seen.index("예비-1") < seen.index("예비-2")


def test_예비를_다_쓰면_그때_회차를_접는다(monkeypatch):
    """폴백이 무한 재시도로 바뀌면 안 된다. 다 떨어지면 종전처럼 미게시다."""
    stub_calls(monkeypatch, limited={"주-모델", "예비-1"})
    out = S.summarize_all(ARTICLES, model="주-모델", pause=0, max_calls=50,
                          fallback_models=["예비-1"])
    assert not any(a["llm_done"] for a in out)


def test_폴백이_없으면_종전과_같다(monkeypatch):
    stub_calls(monkeypatch, limited={"주-모델"})
    out = S.summarize_all(ARTICLES, model="주-모델", pause=0, max_calls=50,
                          fallback_models=[])
    assert not any(a["llm_done"] for a in out)


def test_주_모델과_같은_이름은_체인에서_뺀다(monkeypatch):
    """같은 모델을 다시 부르면 같은 한도를 두드리는 것이라 의미가 없다."""
    stub_calls(monkeypatch, limited={"주-모델"})
    out = S.summarize_all(ARTICLES, model="주-모델", pause=0, max_calls=50,
                          fallback_models=["주-모델"])
    assert not any(a["llm_done"] for a in out)


def test_환경변수로_체인을_덮어쓸_수_있다(monkeypatch):
    """Actions에서 코드 수정 없이 바꿀 수 있어야 한다."""
    monkeypatch.setenv("LLM_FALLBACK_MODELS", "환경-1, 환경-2")
    seen = stub_calls(monkeypatch, limited={"주-모델"})
    S.summarize_all(ARTICLES, model="주-모델", pause=0, max_calls=50)
    assert "환경-1" in seen


def test_한도에_안_걸리면_주_모델만_쓴다(monkeypatch):
    seen = stub_calls(monkeypatch, limited=set())
    S.summarize_all(ARTICLES, model="주-모델", pause=0, max_calls=50,
                    fallback_models=["예비-1"])
    assert set(seen) == {"주-모델"}


def test_기본_체인이_groq에_있다():
    """설정을 비워도 동작해야 한다. 주 모델과 겹치지 않아야 의미가 있다."""
    chain = S.FALLBACK_MODELS["groq"]
    assert chain, "groq 기본 체인이 비어 있다"
    assert S.DEFAULT_MODELS["groq"] not in chain


def test_qwen은_체인_뒤쪽에_둔다():
    """qwen3.8은 글이 좋지만 다른 나라 문자가 자주 섞인다. 섞이면 재생성과 번역
    치환으로 호출을 더 쓴다. 폴백은 호출이 모자라서 오는 자리다. 게다가
    why_model이 qwen이라 그 예산은 이미 기사 수만큼 깎여 있다."""
    chain = S.FALLBACK_MODELS["groq"]
    qwen = [i for i, m in enumerate(chain) if "qwen" in m]
    assert qwen, "qwen이 체인에 없다"
    assert qwen[0] > 0, f"qwen이 첫 예비로 와 있다: {chain}"
