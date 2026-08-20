"""add-public-apis-feeds 회귀 테스트 — API 카탈로그.

public-apis(본가)·public-apis-4Kr(한국판)의 README 전체를 파싱해
docs/data/apis.json 스냅샷을 만든다. 커밋 피드 방식(1차 시도)은 이미 등록된
API가 안 보여서 폐기 — 매 회차 전체 목록을 다시 긁어 갱신한다.
"""
import json
import os
from unittest.mock import MagicMock, patch

from news import apis_catalog

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 본가 형식: 목차(## Index) 이전의 스폰서 표 + 5열 표(Auth 백틱, HTTPS/CORS)
GLOBAL_MD = """# Public APIs

### APIs Covered Under Sponsor Suite!
| API | Description | Auth | HTTPS | CORS |
|:---|:---|:---|:---|:---|
| [SponsorAPI](https://sponsor.test/) | Paid sponsor row | `apiKey` | Yes | Yes |

## Index
* [Animals](#animals)

### Animals
API | Description | Auth | HTTPS | CORS
|:---|:---|:---|:---|:---|
| [Cat Facts](https://catfact.ninja/) | Random cat facts | No | Yes | Yes |
| [Cats](https://docs.thecatapi.com/) | Pictures of cats | `apiKey` | Yes | No |

**[⬆ Back to Index](#index)**
"""

# 한국판 형식: ## 목차 + 3열 표(인증만)
KR_MD = """# Public APIs 한국판

## 목차
- [교통](#교통)

### 교통
| API | 설명 | 인증 |
|---|---|---|
| [ITS 국가교통정보센터](https://its.go.kr/) | 실시간 교통정보 | `apiKey` |
| [지하철 API](https://subway.test/) | 지하철 도착정보 | No |
"""


def test_parse_extracts_rows_after_toc():
    apis = apis_catalog.parse(GLOBAL_MD, "global")
    names = [a["name"] for a in apis]
    assert names == ["Cat Facts", "Cats"]
    assert all(a["cat"] == "Animals" for a in apis)
    assert all(a["src"] == "global" for a in apis)


def test_parse_excludes_sponsor_table_before_toc():
    apis = apis_catalog.parse(GLOBAL_MD, "global")
    assert not any(a["name"] == "SponsorAPI" for a in apis)


def test_parse_auth_normalized():
    apis = apis_catalog.parse(GLOBAL_MD, "global")
    by = {a["name"]: a for a in apis}
    assert by["Cat Facts"]["auth"] == ""        # No → 빈 값 (인증 불필요)
    assert by["Cats"]["auth"] == "apiKey"       # 백틱 벗김


def test_parse_kr_three_column_format():
    apis = apis_catalog.parse(KR_MD, "kr")
    assert [a["name"] for a in apis] == ["ITS 국가교통정보센터", "지하철 API"]
    assert apis[0]["desc"] == "실시간 교통정보"
    assert apis[0]["auth"] == "apiKey"
    assert apis[0]["cat"] == "교통"


def _fake_get(md_by_url):
    def get(url, **kw):
        resp = MagicMock()
        body = md_by_url[url]
        resp.text = body if isinstance(body, str) else ""
        resp.json = MagicMock(return_value=body)
        resp.raise_for_status = MagicMock()
        return resp
    return get


def _md_map(global_md=GLOBAL_MD, kr_md=KR_MD):
    """소스 3종(README 2 + LLM data.json)을 모두 채운다 — 하나라도 빠지면 sync 실패."""
    body = {"readme": {"global": global_md, "kr": kr_md}}
    return {s["url"]: (LLM_JSON if s["kind"] == "llm_json" else body["readme"][s["id"]])
            for s in apis_catalog.SOURCES}


def test_sync_writes_catalog(tmp_path, monkeypatch):
    # 픽스처는 실제 README보다 훨씬 작다 — 형식 변경 가드를 끄고 쓰기 경로만 검증
    monkeypatch.setattr(apis_catalog, "MIN_COUNT", {})
    out = tmp_path / "apis.json"
    with patch.object(apis_catalog.requests, "get", side_effect=_fake_get(_md_map())):
        assert apis_catalog.sync(str(out)) is True
    cat = json.loads(out.read_text(encoding="utf-8"))
    assert len(cat["apis"]) == 6                  # README 4건 + LLM 제공자 2건
    assert {s["id"] for s in cat["sources"]} == {"global", "kr", "llm"}
    assert cat["updated"]


def test_sync_failure_keeps_existing_file(tmp_path):
    out = tmp_path / "apis.json"
    out.write_text('{"apis": [{"name": "기존"}]}', encoding="utf-8")
    with patch.object(apis_catalog.requests, "get",
                      side_effect=apis_catalog.requests.RequestException("down")):
        assert apis_catalog.sync(str(out)) is False
    assert json.loads(out.read_text(encoding="utf-8"))["apis"][0]["name"] == "기존"


def test_sync_rejects_suspiciously_small_result(tmp_path, monkeypatch):
    # README 형식이 바뀌어 파싱이 거의 안 되면 기존 파일을 덮어쓰지 않는다
    out = tmp_path / "apis.json"
    out.write_text('{"apis": [{"name": "기존"}]}', encoding="utf-8")
    with patch.object(apis_catalog.requests, "get", side_effect=_fake_get(_md_map())):
        assert apis_catalog.sync(str(out)) is False   # 픽스처 2건 < MIN_COUNT
    assert json.loads(out.read_text(encoding="utf-8"))["apis"][0]["name"] == "기존"


def test_template_api_view(tmp_path):
    from news.render import render

    with open(os.path.join(ROOT, "sample.json"), encoding="utf-8") as f:
        articles = json.load(f)
    out = tmp_path / "index.html"
    render(articles, str(out))
    html = out.read_text(encoding="utf-8")
    assert 'data-v="api"' in html                 # 레일 버튼
    assert "data/apis.json" in html               # 카탈로그 지연 fetch
    assert "무료 API 목록" in html                 # 전용 뷰 제목
    # 2단 구조 (api-category-hub): 카테고리 허브 → 항목 아코디언
    assert "apiHubHTML" in html                   # 허브(카테고리 카드 그리드)
    assert "apiCatIcon" in html                   # 카테고리 의미 아이콘 (첫 글자 타일 대체)
    assert "apiGroupOf" in html                   # 대분류 색상 섹션 (api-hub-groups)
    assert "aitem" in html                        # 항목 아코디언 행
    assert 'id="apibody"' in html                 # IME 보존용 본문 부분 갱신 컨테이너


def _api_html(tmp_path):
    from news.render import render

    with open(os.path.join(ROOT, "sample.json"), encoding="utf-8") as f:
        articles = json.load(f)
    out = tmp_path / "index.html"
    render(articles, str(out))
    return out.read_text(encoding="utf-8")


def test_ai_llm_is_its_own_top_group(tmp_path):
    """api-ai-llm-group: AI/LLM이 '개발·데이터'에 묻히지 않고 독립 대분류로 뜬다."""
    html = _api_html(tmp_path)
    assert "'AI · LLM'" in html
    # 첫 매칭 우선이므로 dev(개발·데이터)보다 앞에 정의돼야 한다
    assert html.index("'AI · LLM'") < html.index("'개발 · 데이터'")


def test_misleading_cat_name_gets_display_alias(tmp_path):
    """'Machine Learning'은 ML 보조 도구로 오해되므로 표시명에 AI·LLM을 붙인다."""
    html = _api_html(tmp_path)
    assert "A_CAT_ALIAS" in html
    assert "apiCatLabel" in html
    assert "AI · LLM · 머신러닝" in html


def test_api_search_matches_alias(tmp_path):
    """검색은 원본 카테고리명뿐 아니라 별칭에도 걸린다 (LLM으로 검색 가능)."""
    html = _api_html(tmp_path)
    assert "apiCatLabel(x.cat)" in html


# ---------------- api-free-llm-source: 무료 LLM 전용 소스 ----------------
# mnfst/awesome-free-llm-apis 의 data.json 스키마 축약본.
# README 파싱이 아니라 유지보수되는 JSON을 그대로 받는다.
LLM_JSON = {
    "lastUpdated": "2026-08-19",
    "providers": [
        {
            "name": "Groq",
            "url": "https://console.groq.com/keys",
            "description": "Free tier, no credit card. Ultra-fast LPU inference.",
            "models": [
                {"name": "llama-3.3-70b-versatile", "rateLimit": "30 RPM, 1,000 RPD"},
                {"name": "llama-3.1-8b-instant", "rateLimit": "30 RPM, 14,400 RPD"},
                {"name": "openai/gpt-oss-120b", "rateLimit": "30 RPM, 1,000 RPD"},
                {"name": "openai/gpt-oss-20b", "rateLimit": "30 RPM, 1,000 RPD"},
            ],
        },
        {
            "name": "Cohere",
            "url": "https://dashboard.cohere.com/api-keys",
            "description": "Trial key, no credit card.",
            "models": [{"name": "command-r-plus", "rateLimit": "20 RPM"}],
        },
    ],
}


def test_parse_llm_json_one_row_per_provider():
    """제공자 1줄 — 모델별로 펼치지 않는다 (기존 아코디언 UI 유지)."""
    apis = apis_catalog.parse_llm_json(LLM_JSON, "llm")
    assert [a["name"] for a in apis] == ["Groq", "Cohere"]
    assert apis[0]["url"] == "https://console.groq.com/keys"
    assert all(a["cat"] == "AI · LLM" for a in apis)
    assert all(a["src"] == "llm" for a in apis)


def test_parse_llm_json_uses_modal_rate_limit():
    """대표 한도 = 모델 rateLimit 최빈값 (Groq는 1,000 RPD 가 3/4)."""
    groq = apis_catalog.parse_llm_json(LLM_JSON, "llm")[0]
    assert "30 RPM, 1,000 RPD" in groq["desc"]
    assert "30 RPM, 14,400 RPD" not in groq["desc"]   # 최빈값만
    assert "모델 4개" in groq["desc"]


def test_parse_llm_json_requires_api_key():
    """무료 티어라도 키는 필요 — '인증 불필요' 배지가 붙으면 안 된다."""
    assert all(a["auth"] == "apiKey" for a in apis_catalog.parse_llm_json(LLM_JSON, "llm"))


def test_llm_source_registered_with_floor():
    src = {s["id"]: s for s in apis_catalog.SOURCES}
    assert src["llm"]["kind"] == "llm_json"
    assert apis_catalog.MIN_COUNT["llm"] >= 10   # 스키마 변경 시 기존 파일 보존


def test_template_has_llm_segment(tmp_path):
    html = _api_html(tmp_path)
    assert "llm:'무료 LLM'" in html      # A_LBL
    assert "['llm','무료 LLM']" in html   # 세그먼트 필터
