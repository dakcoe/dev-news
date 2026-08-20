# EXEC_PLAN: api-llm-dedupe

- **타입**: fix
- **프로젝트**: project/dev-news
- **상태**: IN_PROGRESS

## 목표

`AI · LLM` 대분류에 Groq·Google Gemini·Hugging Face 가 두 번 나온다 —
새 무료 LLM 소스(제공자 1줄 + 대표 한도)와 public-apis README 의
`Machine Learning` 카테고리가 겹친다. README 쪽 중복을 지운다.

## 접근법

무료 LLM 소스가 이긴다 — 대표 한도·모델 수까지 들어 있어 정보량이 많고
일 단위로 갱신된다. README 쪽은 이름·설명 한 줄뿐이다.

**중요:** 이름만으로 전역 제거하면 안 된다. `Cryptocurrency | Gemini`
(암호화폐 거래소)는 Google Gemini 와 완전히 다른 API 인데 이름이 겹친다.
따라서 **AI/ML 계열 카테고리 안에서만** 중복을 제거한다 — 판정 정규식은
template.html 의 `AI · LLM` 대분류 규칙을 파이썬으로 옮겨 맞춘다.

이름 비교는 영숫자만 남긴 소문자 정규화 (`Hugging Face` == `hugging face`).

## 단계별 계획

1. (RED) tests: 중복 제거 · 암호화폐 Gemini 보존 · 비AI 카테고리 보존 · 소스 건수 반영
2. apis_catalog.py: `_AI_CAT_RE`, `_norm_name()`, `dedupe_llm_overlap()` 추가
3. build_catalog(): 소스별 수집 → dedup → 제거 후 건수로 sources[].count 산출
4. verify-task → 커밋 → complete-task → 푸시

## 완료 기준

- `AI · LLM` 대분류에서 Groq/Google Gemini/Hugging Face 가 각각 1건
- `Cryptocurrency | Gemini` 는 그대로 남는다
- 상단 요약문의 소스별 건수가 제거 후 값과 일치
- pytest 전체 통과
