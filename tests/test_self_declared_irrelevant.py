"""drop-self-declared-irrelevant: 요약이 스스로 무관하다고 말한 기사를 뺀다.

정규식 하나가 게재 여부를 가른다. 넓히면 멀쩡한 기사가 사라지고, 좁히면
아무것도 안 걸린다. 아래 문장은 전부 docs/data/articles/ 에 실제로 있던
`왜중요` 다 — 지어낸 문장으로 이 경계를 박아 두면 아무것도 지키지 못한다.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from news.core.filters import drop_self_declared_irrelevant  # noqa: E402


def _run(*whys):
    kept, dropped = drop_self_declared_irrelevant([{"why": w} for w in whys])
    return [a["why"] for a in kept], [a["why"] for a in dropped]


def test_무관하다고_말한_기사를_뺀다():
    _, dropped = _run(
        "백엔드 개발자의 업무와 무관한 영화 비하인드 스토리다.",
        "이 기사는 미국 문화와 산업 구조를 다루며 백엔드나 AI 개발 업무와"
        " 직접적인 관련이 없다.",
        "백엔드 개발자의 업무 도구나 시스템 아키텍처와 무관한 소비자 대상"
        " 교육 프로그램이다.",
        "조류 관측 데이터는 백엔드 개발과 무관하므로 이 기사는 독자의 업무에"
        " 직접적인 영향을 주지 않는다.",
    )
    assert len(dropped) == 4


def test_조건절의_무관은_걸리지_않는다():
    """'무관' 한 단어로 찾으면 이런 문장이 걸린다. 주어가 개발자·개발이고
    서술이 무관·관련없음인 판정문만 본다."""
    kept, dropped = _run(
        "위험이 높으면 유출 확인과 무관하게 72시간 내 사용자에게 통보해야 한다.",
        "LLM 결과 검증 없이 전달만 하는 방식은 모델 발전과 무관하게 유효하지 않다.",
        "Safe Browsing이나 VirusTotal과 같은 공개 보안 검사 결과와 무관하게"
        " 내려질 수 있다.",
    )
    assert dropped == []
    assert len(kept) == 3


def test_왜중요가_비었으면_남긴다():
    """요약이 실패해 why가 없는 기사까지 빼면 LLM 장애가 곧 게재 중단이 된다."""
    kept, dropped = _run("", None)
    assert dropped == []
    assert len(kept) == 2


def test_줄바꿈이_끼어도_잡는다():
    """왜중요는 여러 줄로 온다. 공백을 눌러 한 줄로 만든 뒤 본다."""
    _, dropped = _run("백엔드 개발자의 업무와\n  무관한\n종이책 분할 기법이다.")
    assert len(dropped) == 1


def test_주어가_개발자가_아니면_놓친다():
    """실측된 한계다. 이 둘은 빠졌어야 할 기사인데 남는다. 주어 조건을 풀면
    위 조건절 세 문장이 같이 걸리므로, 놓치는 쪽을 택했다. 기록해 둔다."""
    kept, _ = _run(
        "사회적 영향 사례 모음집이므로 실무 적용과는 무관하다.",
        "이 기사는 풍자적 콘텐츠로, 실제 기술적 조치나 산업 변화와 무관하다.",
    )
    assert len(kept) == 2
