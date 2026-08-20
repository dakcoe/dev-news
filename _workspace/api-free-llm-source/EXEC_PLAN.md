# EXEC_PLAN: api-free-llm-source

- **타입**: feat
- **프로젝트**: project/dev-news
- **상태**: IN_PROGRESS

## 목표

무료 LLM API(Groq·OpenRouter·Cerebras·Mistral…) 커버리지를 채운다.
public-apis README는 커뮤니티 갱신 속도를 못 따라가 `Machine Learning` 35개 중
대부분이 구형 비전 API다. 기계가 읽는 전용 소스를 3번째 소스로 추가한다.

## 접근법

소스: `mnfst/awesome-free-llm-apis` 의 **`data.json`** (⭐6.8k, 일 단위 갱신,
`.verify/` 로 엔드포인트 생존 자동 검증, "영구 무료 티어만" 정책).
README 파싱이 아니라 **유지보수되는 JSON 스키마를 그대로 받는다** — 형식 변경
취약성이 훨씬 낮다.

표현 방식(사용자 결정): **제공자 1줄 + 대표 한도.** 모델별 행으로 펼치지 않아
기존 아코디언 UI가 그대로 유지된다.

- `name` = 제공자명, `url` = API 키 발급 페이지
- `desc` = 원문 설명 · 대표 한도 · 모델 n개 (대표 모델 3개)
- 대표 한도 = 제공자 모델들의 `rateLimit` **최빈값** (17곳 중 13곳은 단일값,
  나머지도 최빈값이 명확) — 동률이면 첫 모델 값
- `auth` = `apiKey` (무료 티어라도 키는 필요 → "인증 불필요" 배지 안 붙음)
- `cat` = `AI · LLM` → api-ai-llm-group 에서 만든 대분류가 그대로 받는다
- `src` = `llm`

## 단계별 계획

1. (RED) tests/test_api_feeds.py: JSON 파서·대표 한도·MIN_COUNT 방어·UI 세그 테스트
2. apis_catalog.py: SOURCES 에 `kind` 도입 (readme|llm_json), `parse_llm_json()` 추가
3. MIN_COUNT["llm"]=10 — 스키마 변경 시 기존 파일 보존
4. template.html: A_LBL 에 llm 추가, 세그 버튼 4개로, 상단 요약문 소스 기반으로
5. verify-task → 커밋 → complete-task → 푸시

## 완료 기준

- `sync()` 후 apis.json 에 src=llm 항목 17건 내외, Groq/OpenRouter/Mistral 포함
- 허브 `AI · LLM` 섹션에 `AI · LLM` 카테고리 카드가 뜨고 대표 한도가 보인다
- 세그먼트에 '무료 LLM' 필터 동작
- pytest 전체 통과
