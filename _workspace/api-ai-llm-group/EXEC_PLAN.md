# EXEC_PLAN: api-ai-llm-group

- **타입**: feat
- **프로젝트**: project/dev-news
- **상태**: IN_PROGRESS
- **생성일**: 2026-08-20T05:58:27.044Z

## 목표

Groq·Gemini·Hugging Face 같은 LLM/생성형 AI API가 "Machine Learning" 카테고리에
묻혀 있어 *ML을 보조하는 도구* 로 오해된다. 카탈로그 허브에서 AI/LLM을
독립 대분류로 끌어올리고, 오해를 부르는 업스트림 카테고리명에 표시용 별칭을 붙인다.

## 접근법

카테고리명은 public-apis README(업스트림)가 소유하므로 **데이터는 손대지 않고
표시 계층(template.html)에서만** 해결한다.

1. `A_GROUPS` 맨 앞에 `ai` 대분류("AI · LLM") 추가 — 첫 매칭 우선이므로
   기존 `dev`(개발·데이터) 정규식은 그대로 두어도 AI 계열이 먼저 잡힌다.
2. `A_CAT_ALIAS` 표시용 별칭 맵 도입 — `Machine Learning` → `AI · LLM · 머신러닝`.
   원본 `x.cat`은 필터 키로 그대로 쓰고, 화면 문자열만 `apiCatLabel()`로 감싼다.
3. 검색은 원본명·별칭 양쪽에 매칭시켜 "LLM"으로 검색해도 걸리게 한다.

## 단계별 계획

1. (RED) tests/test_api_feeds.py 에 대분류·별칭·검색 회귀 테스트 추가 → 실패 확인
2. template.html: `A_CAT_ALIAS` / `apiCatLabel()` 추가, 허브 카드·아코디언
   그룹 헤더·검색 필터가 별칭을 쓰도록 수정
3. template.html: `A_GROUPS` 에 `ai` 대분류 추가 (dev 앞)
4. `node scripts/verify-task.js project/dev-news` 통과 확인
5. 커밋 → complete-task

## 완료 기준

- 허브 최상단 근처에 "AI · LLM" 색상 섹션이 별도로 보이고 Machine Learning /
  AI & 머신러닝 카테고리가 그 안에 들어간다
- 카드·그룹 헤더에 `AI · LLM · 머신러닝` 로 표시된다 (원본 데이터는 불변)
- 검색창에 `LLM` 입력 시 해당 카테고리 항목이 나온다
- pytest 전체 통과
