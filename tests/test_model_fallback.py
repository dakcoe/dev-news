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


# ---------------- 사다리 ----------------

def test_사다리는_하나다():
    """요약과 왜중요는 같은 사다리를 쓰고 들어가는 칸만 다르다. 둘을 따로 두면
    한쪽만 고쳐져 어긋난다."""
    assert S.MODEL_LADDER["groq"] == [
        "openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b"]


def test_요약은_사다리_맨_위부터_내려간다():
    top = S.DEFAULT_MODELS["groq"]
    assert top == S.MODEL_LADDER["groq"][0]
    assert S.chain_below("groq", top) == ["qwen/qwen3.8-27b", "openai/gpt-oss-20b"]


def test_왜중요는_qwen38에서_시작해_나머지를_좋은_순으로():
    """아래 칸만 주면 더 나은 120b 를 못 쓴다. 나머지 전부를 사다리 순으로."""
    assert S.chain_below("groq", "qwen/qwen3.8-27b") == ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]


def test_맨_아래_칸에서도_위_칸들을_예비로_쓴다():
    assert S.chain_below("groq", "openai/gpt-oss-20b") == ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"]


def test_사다리에_없는_모델이면_사다리_전체를_쓴다():
    """config에서 사다리 밖 모델을 지정해도 폴백은 살아 있어야 한다."""
    assert S.chain_below("groq", "바깥-모델") == S.MODEL_LADDER["groq"]


def test_사다리에_없는_모델을_적지_않는다():
    """계정에서 쓸 수 있는 모델만 적어야 한다. 없는 이름이면 404로 죽는다.
    2026-09-18 기준 목록이다 — qwen3.6-27b 는 이날 내려갔다."""
    AVAILABLE = {"openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"}
    unknown = set(S.MODEL_LADDER["groq"]) - AVAILABLE
    assert not unknown, f"사다리에 없는 모델: {unknown}"


# ---------------- 없는 모델 (404) ----------------

def test_없는_모델은_재시도하지_않고_바로_버린다(monkeypatch):
    """2026-09-14 22:38 회차에서 체인에 없는 이름을 적어 기사마다 3회씩
    재시도했다. 호출 12회를 태우고 4건이 미게시됐다. 404는 재시도해도 같은
    답이므로 즉시 다음 모델로 넘어간다."""
    seen = []

    def fake_call(prompt, provider, model, api_key):
        seen.append(model)
        if model == "없는-모델":
            raise S.ModelGone(model)
        return "번역제목: 제목\n요약: 요약이다.\n왜중요: 이유다."

    monkeypatch.setattr(S, "_call", fake_call)
    monkeypatch.setattr(S.time, "sleep", lambda *a: None)
    out = S.summarize_all(ARTICLES, model="없는-모델", pause=0, max_calls=50,
                          fallback_models=["살아있는-모델"])

    assert seen.count("없는-모델") == 1, f"재시도했다: {seen}"
    assert all(a["llm_done"] for a in out)


def test_없는_모델뿐이면_회차를_접는다(monkeypatch):
    def fake_call(prompt, provider, model, api_key):
        raise S.ModelGone(model)

    monkeypatch.setattr(S, "_call", fake_call)
    monkeypatch.setattr(S.time, "sleep", lambda *a: None)
    out = S.summarize_all(ARTICLES, model="없는-모델", pause=0, max_calls=50,
                          fallback_models=[])
    assert not any(a["llm_done"] for a in out)


def test_404_응답이_ModelGone으로_올라온다(monkeypatch):
    """Groq의 실제 응답 형태를 그대로 쓴다."""
    class FakeResp:
        status_code = 404
        headers: dict = {}
        text = ('{"error":{"message":"The model `x` does not exist or you do not '
                'have access to it.","type":"invalid_request_error",'
                '"code":"model_not_found"}}')

    monkeypatch.setattr(S.requests, "post", lambda *a, **k: FakeResp())
    try:
        S._call_openai_compatible("p", "x", "k", "http://x")
    except S.ModelGone:
        return
    raise AssertionError("ModelGone이 나오지 않았다")


# ---------------- 사다리 충돌 ----------------

def test_요약이_내려와도_왜중요와_같은_칸에_앉지_않는다(monkeypatch):
    """한 칸을 둘이 쓰면 한 기사에 같은 한도를 두 번 두드린다. 한도를 피해
    내려왔는데 예산을 두 배로 쓰는 꼴이다."""
    seen = []

    def fake_call(prompt, provider, model, api_key):
        seen.append(model)
        if model == "openai/gpt-oss-120b":
            raise S.RateLimited(2)
        return "번역제목: 제목\n요약: 요약이다.\n왜중요: 이유다."

    monkeypatch.setattr(S, "_call", fake_call)
    monkeypatch.setattr(S.time, "sleep", lambda *a: None)
    out = S.summarize_all(ARTICLES, pause=0, max_calls=90,
                          why_model="qwen/qwen3.8-27b")

    assert all(a["llm_done"] for a in out)
    # 요약이 qwen3.8로 내려왔으니 왜중요는 gpt-oss-20b 로 비켜야 한다
    assert "openai/gpt-oss-20b" in seen


def test_exclude_는_여전히_뺀다():
    chain = S.chain_below("groq", "사다리밖", exclude={"openai/gpt-oss-120b"})
    assert chain == ["qwen/qwen3.8-27b", "openai/gpt-oss-20b"]


def test_한도에_걸린_모델로는_왜중요도_안_간다(monkeypatch):
    """요약이 120b 한도로 qwen3.8 에 내려오면 왜중요는 비켜야 하는데, 그 예비
    첫 칸이 120b 다. 방금 한도에 걸린 모델이니 건너뛰고 20b 로 가야 한다."""
    seen = []

    def fake_call(prompt, provider, model, api_key):
        seen.append(model)
        if model == "openai/gpt-oss-120b":
            raise S.RateLimited(2)
        return "번역제목: 제목\n요약: 요약이다.\n왜중요: 이유다."

    monkeypatch.setattr(S, "_call", fake_call)
    monkeypatch.setattr(S.time, "sleep", lambda *a: None)
    out = S.summarize_all(ARTICLES, pause=0, max_calls=90, why_model="qwen/qwen3.8-27b")
    assert all(a["llm_done"] for a in out)
    assert "openai/gpt-oss-20b" in seen
    # 한도에 걸린 뒤로는 120b 를 다시 부르지 않는다 (처음 재시도 몇 번만)
    assert seen.count("openai/gpt-oss-120b") <= S.MAX_429_RETRIES + 1


def test_모델을_바꾸면_재생성_기회도_새로_준다(monkeypatch):
    """예전에는 retries_429만 되돌리고 attempt는 남겨, 새 모델이 첫 응답에서
    외국 문자를 내면 재생성 없이 바로 치환으로 갔다."""
    import re
    src = open(os.path.join(ROOT, "news", "summarizer.py"), encoding="utf-8").read()
    body = src[src.index("def summarize_all("):]
    for m in re.finditer(r"model = chain\.pop\(0\)(.{0,200})", body, re.S):
        assert "attempt = 0" in m.group(1), "모델 교체 후 attempt를 되돌리지 않는다"
