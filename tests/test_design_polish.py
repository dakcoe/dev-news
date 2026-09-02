"""디자인 다듬기 (design-polish-readability) — 레퍼런스 규칙 회귀 방지."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(ROOT, "news", "template.html"), encoding="utf-8") as f:
    TEMPLATE = f.read()


def _rule(selector):
    m = re.search(re.escape(selector) + r"\{([^}]*)\}", TEMPLATE)
    assert m, f"{selector} 규칙이 없다"
    return m.group(1)


def test_card_shadow_tokens_exist():
    # SF-01 Beautiful Shadows: 다단 레이어 그림자 토큰
    assert "--shadow-card:" in TEMPLATE
    assert "--shadow-card-hover:" in TEMPLATE


def test_row_uses_shadow_not_border():
    rule = _rule(".row")
    assert "var(--shadow-card)" in rule
    assert "border:1px solid" not in rule, "카드 보더는 그림자로 대체한다 (ai-slop-catalog)"


def test_snip_line_length_capped():
    # RF Layout: 장행 가독성 — 스니펫 줄 길이 제한
    assert re.search(r"\.snip\{[^}]*max-width:\s*\d+ch", TEMPLATE)


def test_no_ai_slop_patterns():
    # Diff Ledger 지양 목록: 사이드탭 액센트 보더(두꺼운 한쪽 컬러 보더)
    assert not re.search(r"border-left:\s*[3-9]px solid", TEMPLATE)
    # 바운스 이징
    assert "cubic-bezier(0.68" not in TEMPLATE and "elastic" not in TEMPLATE
