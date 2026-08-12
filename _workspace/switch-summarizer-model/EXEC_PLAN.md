# EXEC_PLAN: switch-summarizer-model

- **타입**: feat
- **프로젝트**: project/dev-news
- **상태**: IN_PROGRESS

## 목표

요약 모델을 `llama-3.3-70b-versatile` → `openai/gpt-oss-120b`로 바꾼다.
같은 기사·같은 프롬프트 A/B 실측 결과를 근거로 한다. Groq 안에서의 교체이므로
"Groq 전용, 새 공급자 추가 금지"(SPEC 불변 제약)에 걸리지 않는다.

## A/B 실측 (동일 기사 10건, 동일 프롬프트)

가장 큰 차이는 **번역 정확도**다.

> 원제: `Company Offering '100% Human-Written, Never AI' Medical Research Is 100% AI`
> - llama: "Research Gold / 연구골드 — 의학 연구를 위한 논문 초안 및 체계적 리뷰 제공"
>   → 기사의 핵심(실제로는 100% AI라는 폭로)이 통째로 사라졌다
> - gpt-oss: "100% 인간이 쓴, AI는 절대 쓰지 않는다는 의료 연구 서비스가 실제로는 100% AI"

| 항목 | llama-3.3-70b | gpt-oss-120b |
|------|---------------|--------------|
| 오역 | "전문 메소도론가"(methodologist) | "방법론자" |
| 비문 | "있음을모르다하다" | "신원이 무단으로 사용되고 있음을 모른다" |
| 왜중요 | "…중요한 의미를 가진다" 동어반복 다수 | 구체적 판단 근거 |
| 요약 정보밀도 | 낮음 | Tauri 2·Atomic Save 등 구체 정보 포함 |
| 평균 응답 | 1.1s | 1.6s |

## 전환에 필요한 코드 변경 3가지

**① `reasoning_effort: "low"`** — gpt-oss는 추론형이라 `max_tokens`를 추론 토큰이
다 쓰면 `content`가 **빈 문자열**로 온다. 첫 시행에서 10건 중 2건이 이렇게 실패했다.
`reasoning_effort=low`를 주면 10/10 성공한다.

**② 외국문자 검사 오탐 제거** — gpt-oss 산출물에서 `FOREIGN_RE`가 잡은 문자는
전부 무해했다. **U+202F(좁은 비분리 공백) 12건, U+2192(→) 1건**. 한자·가나·키릴은
0건이다. 이대로 두면 정상 산출물이 "외국 문자 섞임"으로 재생성되고, 재생성해도
남으면 미게시된다 — LLM 예산을 태우고 좋은 기사를 떨어뜨린다.

공백류는 ASCII 공백으로 정규화하고(저장물도 깨끗해진다), 화살표는 허용집합에
넣는다(`SVG→PDF`처럼 쓸모가 있다). 한자·가나·키릴 차단은 그대로 유지한다.

**③ 호출 간격** — gpt-oss는 무료 한도(429)에 llama보다 빨리 걸린다. 2초 간격에서
10건 중 5건이 429였고 8초에서 10/10 성공했다. `config.yaml`로 뺀다.

## 단계별 계획

1. 테스트 작성(RED) — 공백 정규화·화살표 허용·한자 차단 유지·gpt-oss 페이로드
2. `summarizer.py` — `_normalize_symbols()`, `FOREIGN_RE` 조정, `reasoning_effort`
3. `config.yaml` — `llm.model`·`llm.pause_seconds`, `build.py`가 전달
4. 실호출 스모크 — 5건으로 종단 확인
5. verify → 커밋 → complete

## 완료 기준

- [ ] gpt-oss 호출에 `reasoning_effort=low`가 실린다 (빈 content 0건)
- [ ] U+202F·U+2192가 재생성을 유발하지 않는다
- [ ] 한자·가나·키릴은 여전히 차단된다 (기존 test_foreign_leak.py 통과)
- [ ] 저장물에 U+202F가 남지 않는다 (ASCII 공백으로 정규화)
- [ ] 모델·간격이 config로 바뀐다 (`vars.LLM_MODEL`도 계속 우선)
- [ ] 기존 테스트 전부 통과 + ruff 통과
