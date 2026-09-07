"""'왜 중요한가'만 다른 모델로 뽑는 경로 (llm.why_model).

번역·요약은 원문을 옮기는 일이라 gpt-oss로 충분하지만, 왜중요는 기사에 없는
판단을 쓰는 일이라 큰 모델을 쓴다. 고정할 것 세 가지:
  ① why_model이 설정되면 기사당 호출이 2회이고, 두 번째 호출만 다른 모델로 간다
  ② 그 호출이 실패해도 기사는 게시된다 — 주 모델이 쓴 왜중요를 그대로 쓴다
  ③ 429면 그 회차 남은 기사는 아예 다시 시도하지 않는다 (예산 낭비 방지)
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from news import summarizer as S  # noqa: E402

MAIN = """번역제목: 테스트 제목
요약: 요약 문장이다.
왜중요: 주 모델이 쓴 한 문장.
분류: 게재
"""

ARTICLE = {"title": "Test title", "source": "hn", "content": "본문이다."}


def _run(monkey_calls, **kw):
    """_call을 가로채고 summarize_all을 한 기사에 대해 돌린다."""
    seen = []

    def fake_call(prompt, provider, model, api_key):
        seen.append(model)
        return monkey_calls(prompt, model)

    orig, S._call = S._call, fake_call
    os.environ["GROQ_API_KEY"] = "test"
    try:
        out = S.summarize_all([dict(ARTICLE)], pause=0, **kw)
    finally:
        S._call = orig
    return out[0], seen


def test_why_model_makes_second_call_with_other_model():
    def calls(prompt, model):
        return "다른 모델이 쓴 두 문장. 그래서 이렇게 하면 된다." if "왜 중요한가" in prompt else MAIN

    art, seen = _run(calls, model="main-model", why_model="why-model")
    assert seen == ["main-model", "why-model"]
    assert art["why"] == "다른 모델이 쓴 두 문장. 그래서 이렇게 하면 된다."
    assert art["llm_done"] is True


def test_why_call_failure_keeps_main_model_why():
    def calls(prompt, model):
        if "왜 중요한가" in prompt:
            raise RuntimeError("HTTP 404: model_not_found")
        return MAIN

    art, _ = _run(calls, model="main-model", why_model="사라진-모델")
    assert art["llm_done"] is True                  # 기사는 살아남는다
    assert art["why"] == "주 모델이 쓴 한 문장."


def test_why_429_stops_further_why_calls():
    def calls(prompt, model):
        if "왜 중요한가" in prompt:
            raise S.RateLimited(30)
        return MAIN

    seen = []

    def fake_call(prompt, provider, model, api_key):
        seen.append(model)
        return calls(prompt, model)

    orig, S._call = S._call, fake_call
    os.environ["GROQ_API_KEY"] = "test"
    try:
        out = S.summarize_all([dict(ARTICLE), dict(ARTICLE)], pause=0,
                              model="main-model", why_model="why-model")
    finally:
        S._call = orig

    assert seen == ["main-model", "why-model", "main-model"]   # 두 번째 기사엔 안 부른다
    assert all(a["llm_done"] for a in out)


def test_parse_why_strips_label_and_no_info():
    assert S._parse_why("왜중요: 한 문장이다.") == "한 문장이다."
    assert S._parse_why("왜 중요한가: 한 문장이다.") == "한 문장이다."
    assert S._parse_why("없음") == ""
    assert S._parse_why("**한 문장이다.**") == "한 문장이다."
