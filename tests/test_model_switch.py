"""요약 모델 교체 회귀 테스트 (switch-summarizer-model).

A/B 실측으로 llama-3.3-70b → openai/gpt-oss-120b로 바꾸면서 드러난 두 가지
함정을 고정한다.
  ① gpt-oss는 추론형이라 reasoning_effort를 낮추지 않으면 content가 빈 문자열로
     온다 (실측 10건 중 2건 실패 → low 적용 후 10/10)
  ② FOREIGN_RE가 gpt-oss 산출물에서 잡은 건 한자·가나가 아니라 U+202F(좁은
     비분리 공백) 12건과 U+2192(→) 1건뿐이었다. 오탐으로 재생성·미게시되면
     LLM 예산을 태우고 좋은 기사를 떨어뜨린다.
"""
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from news import summarizer as S  # noqa: E402


# ------------------------------------------------- ① reasoning_effort
def test_gpt_oss_payload_lowers_reasoning_effort():
    sent = {}

    class FakeResp:
        status_code = 200
        headers: dict = {}

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": "번역제목: 제목\n요약: 요약.\n왜중요: 이유."}}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        sent.update(json)
        return FakeResp()

    S.requests.post, orig = fake_post, S.requests.post
    try:
        S._call_openai_compatible("p", "openai/gpt-oss-120b", "k", "http://x")
        assert sent["reasoning_effort"] == "low"
        sent.clear()
        S._call_openai_compatible("p", "llama-3.3-70b-versatile", "k", "http://x")
        assert "reasoning_effort" not in sent   # 비추론 모델엔 붙이지 않는다
    finally:
        S.requests.post = orig


def test_missing_content_returns_empty_string():
    """추론만 오고 content가 없으면 None이 아니라 ''를 돌려 재시도 경로를 탄다."""
    class FakeResp:
        status_code = 200
        headers: dict = {}

        @staticmethod
        def json():
            return {"choices": [{"message": {"reasoning": "생각 중...", "content": None}}]}

    S.requests.post, orig = (lambda *a, **k: FakeResp()), S.requests.post
    try:
        assert S._call_openai_compatible("p", "openai/gpt-oss-120b", "k", "http://x") == ""
    finally:
        S.requests.post = orig


# ------------------------------------------------- ② 외국문자 오탐
def test_benign_symbols_do_not_trigger_regeneration():
    for ch in (" ", " ", "→", "‑"):
        parsed = S._parse(f"번역제목: SVG{ch}PDF 변환\n요약: 본문{ch}설명이다.\n왜중요: 이유{ch}설명.")
        joined = " ".join(filter(None, [parsed["ko_title"], parsed["summary"], parsed["why"]]))
        assert not S.FOREIGN_RE.search(joined), f"U+{ord(ch):04X}가 재생성을 유발"


def test_narrow_space_normalized_away():
    """저장물에 보이지 않는 공백이 남지 않는다."""
    parsed = S._parse("번역제목: 좁은 공백\n요약: 본문 이다.\n왜중요: 이유.")
    assert " " not in parsed["ko_title"] and " " not in parsed["summary"]
    assert parsed["ko_title"] == "좁은 공백"


def test_arrow_survives_normalization():
    parsed = S._parse("번역제목: SVG→PDF 변환기\n요약: 요약.\n왜중요: 이유.")
    assert "→" in parsed["ko_title"]


def test_real_foreign_scripts_still_blocked():
    """한자·가나·키릴 차단은 그대로 — 이게 뚫리면 원래 막던 사고가 돌아온다."""
    for bad in ("超越", "プロトタイプ", "прогресс", "เทกซ"):
        assert S.FOREIGN_RE.search(bad), bad


# ------------------------------------------------- 설정 배선
def test_default_model_is_gpt_oss():
    assert S.DEFAULT_MODELS["groq"] == "openai/gpt-oss-120b"


def test_config_exposes_model_and_pause():
    cfg = yaml.safe_load(open(os.path.join(ROOT, "config.yaml"), encoding="utf-8"))["llm"]
    assert "model" in cfg                       # 비워두면 기본 모델
    assert float(cfg["pause_seconds"]) >= 5.0   # gpt-oss는 2초에서 429가 절반


def test_build_passes_llm_config():
    src = open(os.path.join(ROOT, "build.py"), encoding="utf-8").read()
    assert 'model=llm_cfg.get("model") or None' in src
    assert 'pause=float(llm_cfg.get("pause_seconds"' in src
