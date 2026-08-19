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
        resp.text = md_by_url[url]
        resp.raise_for_status = MagicMock()
        return resp
    return get


def _md_map(global_md=GLOBAL_MD, kr_md=KR_MD):
    return {s["readme"]: (global_md if s["id"] == "global" else kr_md)
            for s in apis_catalog.SOURCES}


def test_sync_writes_catalog(tmp_path, monkeypatch):
    # 픽스처는 실제 README보다 훨씬 작다 — 형식 변경 가드를 끄고 쓰기 경로만 검증
    monkeypatch.setattr(apis_catalog, "MIN_COUNT", {})
    out = tmp_path / "apis.json"
    with patch.object(apis_catalog.requests, "get", side_effect=_fake_get(_md_map())):
        assert apis_catalog.sync(str(out)) is True
    cat = json.loads(out.read_text(encoding="utf-8"))
    assert len(cat["apis"]) == 4
    assert {s["id"] for s in cat["sources"]} == {"global", "kr"}
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
    assert "aitem" in html                        # 항목 아코디언 행
    assert 'id="apibody"' in html                 # IME 보존용 본문 부분 갱신 컨테이너
