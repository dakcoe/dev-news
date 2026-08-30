"""비개발 기사 차단 필터 (filter-nondev-articles).

재현하는 결함: config의 키워드 140개에 한국어가 0개라 긱뉴스 한국어 제목이
필터를 통과할 수 없었고, 그래서 TRUSTED로 검사를 면제했다. 그 결과 개발과
무관한 기사가 그대로 실렸다 — 2026-08-30 배치 20건 중 4건(텍사스 감시 카메라,
호주 부당해고 판결, 저작권 소송, 대학 학점 실험).

화이트리스트를 넓히는 대신 방향을 뒤집는다: 차단어가 있으면서 **동시에**
개발 키워드가 하나도 없을 때만 뺀다.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from build import keyword_filter  # noqa: E402

KW = ["ai", "llm", "python", "linux", "api", "release", "security", "kernel"]
BLOCK = {
    "ko": ["선거", "국민투표", "대통령", "관세", "감시", "경찰", "기후", "추락", "올림픽"],
    "en": ["election", "president", "war", "tariff", "police", "climate", "olympic"],
}


def _art(title, source="geeknews", description=""):
    return {"title": title, "source": source, "description": description}


def _kept(title, source="geeknews", description=""):
    out = keyword_filter([_art(title, source, description)], KW, BLOCK)
    return len(out) == 1


# ------------------------------------------------------- 차단 정타 (실측 사례)
def test_blocks_nondev_articles():
    for title in ("아이슬란드, EU 가입 협상 재개 여부 국민투표",
                  "캐나다, 대미 무역 협상 중단…미국 관세에 동일 액수로 맞대응",
                  "DHS, 잘 알려지지 않은 세관법으로 언론인·비영리단체·노조 감시",
                  "뉴멕시코 민간 항공기 추락, 미군 GPS 교란과 연관"):
        assert not _kept(title), f"차단돼야 함: {title}"


def test_blocks_when_only_description_matches():
    """차단어가 제목이 아니라 설명에만 있는 경우 — 엘니뇨 기사가 그랬다."""
    assert not _kept("기록적 수준으로 빠르게 성장하는 2026년 슈퍼 엘니뇨",
                     description="전 세계 기후에 강력한 영향을 미치는 대형 현상")


def test_blocks_english_nondev():
    assert not _kept("The president signed a new tariff order", "devto")
    assert not _kept("Olympic broadcast rights sold for a record sum", "devto")


# --------------------------------------------- 개발 키워드 동반 시 통과 (핵심)
def test_dev_keyword_rescues_political_wording():
    """정치 어휘를 쓰지만 개발 기사인 경우 — 실측된 진짜 기사."""
    assert _kept("캘리포니아주 의회, 연령 확인법에서 Linux를 만장일치로 면제")
    assert _kept("California lawmakers pass Linux exemption from age-verification law",
                 "hackernews")


def test_dev_keyword_in_description_also_rescues():
    assert _kept("경찰 시스템 개편", description="새 API 게이트웨이를 도입했다")


# ------------------------------------------------------------- 부분문자열 함정
def test_war_does_not_match_software_or_hardware():
    """`war`가 `software`·`hardware` 안에서 걸렸다 — 실제로 오탐을 냈다."""
    for title in ("Open source software supply chain report",
                  "New hardware benchmark results",
                  "Firmware and hardware co-design"):
        assert _kept(title, "devto"), f"통과해야 함: {title}"


def test_police_does_not_match_policy():
    assert _kept("A new privacy policy for our users", "devto")


def test_korean_ambiguous_words_are_not_in_default_list():
    """`배우`는 `배우다`에 걸린다 — 기본 목록에 있으면 안 된다."""
    import yaml
    with open(os.path.join(ROOT, "config.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    ko = (cfg.get("block_keywords") or {}).get("ko") or []
    for ambiguous in ("배우", "기소", "사찰"):
        assert ambiguous not in ko, f"모호어가 목록에 있음: {ambiguous}"


# ------------------------------------------------------------- TRUSTED에도 적용
def test_block_applies_to_trusted_sources():
    """면제는 통과 조건(화이트리스트)에만 해당한다. 차단은 모두에게 적용된다."""
    for src in ("geeknews", "rss", "github", "devto", "anthropic"):
        assert not _kept("아이슬란드, EU 가입 협상 재개 여부 국민투표", src), \
            f"{src}에서 차단돼야 함"


def test_trusted_still_bypasses_whitelist():
    """개발 키워드가 없어도 TRUSTED는 통과한다 — 기존 동작을 깨지 않는다."""
    assert _kept("The Twelve-Factor App (2011)", "geeknews")
    assert _kept("actions / checkout", "github")


# ------------------------------------------------------------------- 하위 호환
def test_no_block_list_behaves_as_before():
    assert len(keyword_filter([_art("아이슬란드 국민투표")], KW, None)) == 1
    assert len(keyword_filter([_art("아이슬란드 국민투표")], KW, {})) == 1


def test_block_list_without_keywords_still_works():
    assert len(keyword_filter([_art("아이슬란드 국민투표")], [], BLOCK)) == 0


# ------------------------------------------------- 한국어 개발 어휘 구제 (실측)
# 차단어에 걸렸지만 한국어 개발 어휘로 살아나야 하는 진짜 기사들.
# 이 구제가 없을 때 오탐으로 빠졌다.
def test_korean_dev_vocabulary_rescues_real_articles():
    import yaml
    with open(os.path.join(ROOT, "config.yaml"), encoding="utf-8") as f:
        kw = yaml.safe_load(f)["keywords"]

    def kept(title, description=""):
        art = _art(title, "geeknews", description)
        return len(keyword_filter([art], kw, BLOCK)) == 1

    assert kept("FedEx의 진짜 결제 문자가 피싱처럼 보인 이유",
                "관세·세금 납부 SMS가 전형적인 피싱 징후를 갖췄다")
    assert kept("시민 위생 — 경찰국가에 악용될 기술을 만들지 말 것",
                "개발자가 만드는 소프트웨어가 어떻게 쓰일지 생각해야 한다")


def test_config_has_korean_keywords():
    """한국어 키워드가 0개였던 것이 이 문제의 뿌리다 — 회귀 방지."""
    import re as _re
    import yaml
    with open(os.path.join(ROOT, "config.yaml"), encoding="utf-8") as f:
        kw = yaml.safe_load(f)["keywords"]
    korean = [k for k in kw if _re.search(r"[가-힣]", k)]
    assert len(korean) >= 20, f"한국어 키워드가 너무 적다: {len(korean)}개"


def test_ambiguous_korean_dev_words_excluded():
    """`개발`은 부동산 개발에, `테스트`는 백신 테스트에 걸린다."""
    import yaml
    with open(os.path.join(ROOT, "config.yaml"), encoding="utf-8") as f:
        kw = yaml.safe_load(f)["keywords"]
    for ambiguous in ("개발", "테스트", "기술", "모델", "학습"):
        assert ambiguous not in kw, f"모호어가 키워드에 있음: {ambiguous}"
