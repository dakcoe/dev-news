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
                              model="main-model", why_model="why-model",
                              why_fallback_models=[])   # 예비 없이 종전 동작
    finally:
        S._call = orig

    assert seen == ["main-model", "why-model", "main-model"]   # 두 번째 기사엔 안 부른다
    assert all(a["llm_done"] for a in out)


def test_why_429면_예비_왜중요_모델로_갈아탄다():
    """왜중요는 기사에 없는 판단을 쓰는 자리라 글이 좋은 모델을 붙잡는다.
    첫 모델이 한도에 걸리면 끄지 말고 다음 모델로 넘어간다."""
    def fake_call(prompt, provider, model, api_key):
        seen.append(model)
        if "왜 중요한가" in prompt and model == "why-1":
            raise S.RateLimited(30)
        return MAIN

    seen = []
    orig, S._call = S._call, fake_call
    os.environ["GROQ_API_KEY"] = "test"
    try:
        out = S.summarize_all([dict(ARTICLE), dict(ARTICLE)], pause=0,
                              model="main-model", why_model="why-1",
                              why_fallback_models=["why-2"])
    finally:
        S._call = orig

    assert "why-2" in seen
    assert seen.count("why-1") == 1        # 막힌 모델을 다시 부르지 않는다
    assert all(a["llm_done"] for a in out)


def test_parse_why_strips_label_and_no_info():
    assert S._parse_why("왜중요: 한 문장이다.") == "한 문장이다."
    assert S._parse_why("왜 중요한가: 한 문장이다.") == "한 문장이다."
    assert S._parse_why("없음") == ""
    assert S._parse_why("**한 문장이다.**") == "한 문장이다."


def test_왜중요가_더러워도_기사는_게시된다():
    """왜중요는 기사의 부속이다. 거기에 외국 문자가 섞였다고 멀쩡한 요약까지
    버리면 안 된다. 예전에는 세 항목을 합쳐 검사해서 매 회차 기사를 떨궜다."""
    def fake_call(prompt, provider, model, api_key):
        if "왜 중요한가" in prompt:
            return "왜중요: прогресс 진행이다."        # 키릴
        return "번역제목: 제목\n요약: 정상 요약이다.\n왜중요: 주 모델이 쓴 이유다."

    orig, S._call = S._call, fake_call
    os.environ["GROQ_API_KEY"] = "test"
    try:
        out = S.summarize_all([dict(ARTICLE)], pause=0,
                              model="main-model", why_model="why-model")
    finally:
        S._call = orig

    a = out[0]
    assert a["llm_done"], "기사가 떨어졌다"
    assert a["summary"] == "정상 요약이다."
    assert a["why"] == "주 모델이 쓴 이유다.", "주 모델 왜중요로 되돌아가야 한다"
    assert not S.FOREIGN_RE.search(a["why"])


def test_주_모델_왜중요도_더러우면_그_항목만_비운다():
    """되돌아갈 곳이 없으면 왜중요만 버린다. 기사는 그대로 나간다."""
    def fake_call(prompt, provider, model, api_key):
        if "왜 중요한가" in prompt:
            return "왜중요: прогресс 진행이다."
        return "번역제목: 제목\n요약: 정상 요약이다.\n왜중요: 超越 이유다."

    orig, S._call = S._call, fake_call
    os.environ["GROQ_API_KEY"] = "test"
    try:
        out = S.summarize_all([dict(ARTICLE)], pause=0,
                              model="main-model", why_model="why-model")
    finally:
        S._call = orig

    a = out[0]
    assert a["llm_done"]
    assert a["why"] == ""
    assert a["summary"] == "정상 요약이다."


def test_치환_호출의_한도가_주_체인을_태우지_않는다():
    """치환은 보조 수단이다. 그 429가 주 모델용 처리로 새어 나가면 사다리를
    통째로 내려간다 — 기사 2건에 호출 19회, 게시 0건을 만든 적이 있다."""
    calls = []

    def fake_call(prompt, provider, model, api_key):
        calls.append(model)
        if "나열된 단어를 한국어로" in prompt:
            raise S.RateLimited(2)
        return "번역제목: 제목\n요약: カタカナ 섞인 요약.\n왜중요: 이유다."

    orig, S._call = S._call, fake_call
    os.environ["GROQ_API_KEY"] = "test"
    try:
        S.summarize_all([dict(ARTICLE), dict(ARTICLE)], pause=0, max_calls=60,
                        model="main-model", fallback_models=["fb1", "fb2"])
    finally:
        S._call = orig

    assert "fb1" not in calls and "fb2" not in calls, f"사다리가 탔다: {calls}"
    assert len(calls) <= 8, f"호출이 {len(calls)}회로 새고 있다"
