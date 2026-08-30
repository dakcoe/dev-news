# EXEC_PLAN: fix-inference-tag

- **타입**: fix
- **프로젝트**: project/dev-news
- **상태**: COMPLETED

## 목표

로컬 전체 실행(`python build.py --no-ai`, 2026-08-31)에서 발견한 오탐.

  colinhacks / zod
  "TypeScript-first schema validation with static type inference"
  → tags: ai, llm, web, open-source

`llm` 어휘의 `\binference\b`가 **"static type inference"**(TypeScript의 타입
추론)에 걸렸다. TypeScript 검증 라이브러리에 LLM 태그가 붙는다.
`llm`이 붙으면 IMPLIES 규칙으로 `ai`까지 따라온다.

fix-tag-assignment에서 고친 것과 같은 계열이다 — 그때는 요약의 범용어를
막았고, 이번은 어휘 자체가 중의적인 경우다.

## 접근법

`inference`·`추론`을 **약한 패턴으로 옮긴다**(제목에서만 인정).

  타입 추론 · 통계적 추론 · LLM 추론이 같은 단어를 쓴다. 설명·요약에 스치면
  중의적이지만, 제목에 있으면 그 기사의 주제다 — "Fast inference engine"처럼.

어휘에서 지우지는 않는다. 추론 최적화는 이 피드의 핵심 주제 중 하나다.

## 단계별 계획

1. (RED) `tests/test_tag_precision.py`에 회귀 추가 — zod 실사례 · 제목의
   inference는 유지
2. `news/core/tags.py`의 `WEAK_PATTERNS`에 추가
3. 8월 전체 회귀로 영향 확인
4. `node scripts/verify-task.js` → 커밋 → `complete-task.js`

## 완료 기준

- "static type inference"가 llm 태그를 만들지 않는다
- 제목의 inference는 그대로 llm로 잡힌다
- verify-task 통과

## 결과 (2026-08-31)

`\binference\b`·`추론`을 `WEAK_PATTERNS`로 옮겼다(제목에서만 인정).
어휘에서 지우지는 않았다 — 추론 최적화는 이 피드의 핵심 주제다.

8월 전체 회귀: 22/1,272건의 태그가 바뀌고 `llm` 22건 · `ai` 8건이 빠진다.
평균은 2.80 → 2.79로 사실상 그대로다 — 정확히 오탐만 걷혔다.

`scripts/retag.py`로 소급 반영했다.

**이 버그는 로컬 전체 실행으로만 찾을 수 있었다.** 단위 테스트와 부분 스모크로는
안 잡혔고, `python build.py --no-ai`를 실제로 돌려 결과 19건을 눈으로 보다가
`colinhacks / zod`에 llm 태그가 붙은 것을 발견했다. 앞으로 파이프라인을
건드리는 작업은 커밋 전에 전체 실행을 한 번 거치는 편이 낫다.
- **완료일**: 2026-08-30T18:34:19.848Z
