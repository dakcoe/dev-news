"""외국 문자 누출 감지 회귀 테스트 (fix-foreign-script-leak).

한자 전용 필터(HANJA_RE)가 태국 문자·가나·키릴 등을 통과시켜 게시된 실측 사례
(2026-08 게시분: 테็กซ스, 프로토タイプ, まだ, нос고, прогресс)를 재현한다.
화이트리스트 정규식(FOREIGN_RE)이 이들을 전부 잡고, 정상 한국어 문장부호는
오탐하지 않는지 확인한다. HTTP·sleep은 전부 mock — 실제 네트워크 접근 없음.
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


ARTICLES = [{"title": "기사", "url": "https://x/1", "source": "rss", "description": "본문"}]


def test_foreign_scripts_detected():
    # 2026-08 게시분에서 실제로 통과했던 누출 4종 + 히라가나
    leaks = [
        "테็กซ스 주지사에게 보낸 편지",       # 태국 문자
        "SQLite 압축 텍스트 기록 프로토タイプ",  # 가타카나
        "2026년 7월 현재まだ 출시되지 않았다",   # 히라가나
        "기업의 배지들을 нос고 있다",           # 키릴
        "기상 모델이 달성한 прогресс와 일치",   # 키릴
        "제프 딘 离任",                        # 한자 (기존 케이스 회귀)
    ]
    for text in leaks:
        assert summarizer.FOREIGN_RE.search(text), f"미감지: {text}"


def test_normal_korean_not_flagged():
    ok = ("오픈AI가 GPT-5를 공개했다 — 성능이 2.5× 좋아졌고, 가격은 30% 낮다(±3%). "
          "“인용”과 ‘홑따옴표’, 온도 25°C, 가격 ₩1,000·€5·£3·¥700, 목록·구분, 말줄임… "
          "ㄱㄴㄷ 자모와 [대괄호] {중괄호} <꺾쇠>까지 전부 허용된다.")
    assert not summarizer.FOREIGN_RE.search(ok)


def test_katakana_triggers_regeneration(monkeypatch):
    responses = ["번역제목: 프로토タイプ 제안\n요약: 저장 방식을 제안했다.\n왜중요: 크다.",
                 "번역제목: 프로토타입 제안\n요약: 저장 방식을 제안했다.\n왜중요: 크다."]
    calls = []
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(summarizer.time, "sleep", lambda s: None)
    monkeypatch.setattr(summarizer.requests, "post",
                        lambda *a, **k: calls.append(1) or FakeResp(200, responses[len(calls) - 1]))

    out = summarizer.summarize_all(list(ARTICLES), provider="groq", max_calls=10)

    assert len(calls) == 2                       # 외국 문자 감지 → 1회 재생성
    assert out[0]["ko_title"] == "프로토타입 제안"


def test_foreign_repair_translates_and_replaces(monkeypatch):
    """재생성으로도 남으면 한자와 동일하게 번역·일괄 치환으로 복구."""
    leaked = "번역제목: SQLite 프로토タイプ\n요약: 프로토タイプ를 제안했다.\n왜중요: 크다."
    responses = [leaked, leaked, "タイプ=타입"]
    calls = []
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(summarizer.time, "sleep", lambda s: None)
    monkeypatch.setattr(summarizer.requests, "post",
                        lambda *a, **k: calls.append(1) or FakeResp(200, responses[len(calls) - 1]))

    out = summarizer.summarize_all(list(ARTICLES), provider="groq", max_calls=10)

    assert len(calls) == 3
    assert out[0]["llm_done"] is True
    assert out[0]["ko_title"] == "SQLite 프로토타입"
    assert out[0]["summary"] == "프로토타입를 제안했다."


def test_persistent_cyrillic_not_published(monkeypatch):
    """치환 번역까지 실패하면 미게시 — 다음 실행에서 재시도."""
    calls = []
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(summarizer.time, "sleep", lambda s: None)
    monkeypatch.setattr(summarizer.requests, "post",
                        lambda *a, **k: calls.append(1)
                        or FakeResp(200, "번역제목: 배지를 нос고 있다\n요약: 상업화됐다.\n왜중요: 크다."))

    out = summarizer.summarize_all(list(ARTICLES), provider="groq", max_calls=10)

    assert out[0]["llm_done"] is False


def test_trailing_no_info_leak_stripped(monkeypatch):
    """프롬프트 템플릿의 "없음"이 문장 끝에 그대로 붙어 나오는 누출 제거.

    실측: "…협력할 계획이다. 없음" / "기술 스택과 쓰임새에 대한 정보는 없음."
    """
    resp = ("번역제목: 제목\n"
            "요약: 지역 사회와 협력할 계획이다. 없음\n"
            "왜중요: 기술 스택과 쓰임새에 대한 정보는 없음.")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(summarizer.time, "sleep", lambda s: None)
    monkeypatch.setattr(summarizer.requests, "post", lambda *a, **k: FakeResp(200, resp))

    out = summarizer.summarize_all(list(ARTICLES), provider="groq", max_calls=10)

    assert out[0]["llm_done"] is True
    assert out[0]["summary"] == "지역 사회와 협력할 계획이다."
    assert out[0]["why"] == ""


def test_no_info_mid_sentence_kept(monkeypatch):
    """"없음"이 문장 중간에 쓰인 정상 문장은 건드리지 않는다."""
    resp = "번역제목: 제목\n요약: 대안이 없음을 지적하며 새 방식을 제안했다.\n왜중요: 크다."
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(summarizer.time, "sleep", lambda s: None)
    monkeypatch.setattr(summarizer.requests, "post", lambda *a, **k: FakeResp(200, resp))

    out = summarizer.summarize_all(list(ARTICLES), provider="groq", max_calls=10)

    assert out[0]["summary"] == "대안이 없음을 지적하며 새 방식을 제안했다."
