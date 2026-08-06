"""LLM 한도 대응 회귀 테스트 (SPEC 1.6 검수 기준).

429를 강제로 발생시킨 mock에서: 무한 재시도 없이(재시도 2회 상한) 서킷 브레이커가
열리고, 나머지 기사는 호출 시도조차 없이 llm_done=False로 반환되는지 확인한다.
HTTP·sleep은 전부 mock — 실제 네트워크 접근 없음.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from news import summarizer  # noqa: E402


class FakeResp:
    def __init__(self, status, body="", headers=None):
        self.status_code = status
        self.text = body
        self.headers = headers or {}

    def json(self):
        return {"choices": [{"message": {"content": self.text}}]}


ARTICLES = [{"title": f"기사 {i}", "url": f"https://x/{i}", "source": "rss",
             "description": "본문"} for i in range(3)]


def test_429_circuit_breaker(monkeypatch):
    calls = []
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(summarizer.time, "sleep", lambda s: None)
    monkeypatch.setattr(summarizer.requests, "post",
                        lambda *a, **k: calls.append(1) or FakeResp(429, headers={"retry-after": "1"}))

    out = summarizer.summarize_all(list(ARTICLES), provider="groq", max_calls=50)

    # 첫 기사에서 최초 1회 + 재시도 2회 = 3회 후 서킷 오픈, 나머지는 호출 없음
    assert len(calls) == 1 + summarizer.MAX_429_RETRIES
    assert len(out) == 3
    assert all(a["llm_done"] is False for a in out)


def test_budget_cap(monkeypatch):
    calls = []
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(summarizer.time, "sleep", lambda s: None)
    monkeypatch.setattr(summarizer.requests, "post",
                        lambda *a, **k: calls.append(1)
                        or FakeResp(200, "번역제목: 제목\n요약: 새 정보다.\n왜중요: 중요하다."))

    out = summarizer.summarize_all(list(ARTICLES), provider="groq", max_calls=2)

    assert len(calls) == 2                       # 예산 상한에서 멈춘다
    assert [a["llm_done"] for a in out] == [True, True, False]


def test_hanja_triggers_regeneration(monkeypatch):
    responses = ["번역제목: 제프 딘 离任\n요약: 리더십이 교체됐다.\n왜중요: 크다.",
                 "번역제목: 제프 딘 사임\n요약: 리더십이 교체됐다.\n왜중요: 크다."]
    calls = []
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(summarizer.time, "sleep", lambda s: None)
    monkeypatch.setattr(summarizer.requests, "post",
                        lambda *a, **k: calls.append(1) or FakeResp(200, responses[len(calls) - 1]))

    out = summarizer.summarize_all(list(ARTICLES[:1]), provider="groq", max_calls=10)

    assert len(calls) == 2                       # 한자 감지 → 1회 재생성
    assert out[0]["ko_title"] == "제프 딘 사임"
    assert not summarizer.HANJA_RE.search(out[0]["summary"])


def test_no_new_info_becomes_empty_summary(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(summarizer.time, "sleep", lambda s: None)
    monkeypatch.setattr(summarizer.requests, "post",
                        lambda *a, **k: FakeResp(200, "번역제목: 제목\n요약: 없음\n왜중요: 없음"))

    out = summarizer.summarize_all(list(ARTICLES[:1]), provider="groq", max_calls=10)

    # "없음" = 덧붙일 정보 없음 → 빈 문자열로 게시 (UI가 요약 줄을 생략)
    assert out[0]["llm_done"] is True
    assert out[0]["summary"] == ""
    assert out[0]["why"] == ""
