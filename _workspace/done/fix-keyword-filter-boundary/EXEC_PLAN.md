# EXEC_PLAN: fix-keyword-filter-boundary

- **타입**: fix
- **프로젝트**: project/dev-news
- **상태**: COMPLETED

## 목표

`keyword_filter()`가 부분문자열 매칭이라 사실상 무력화된 것을 고친다. 미신뢰 출처
(HN·lobsters)에서 개발·AI와 무관한 기사가 후보로 들어오는 것을 실제로 막는다.

## 배경 — 측정된 결함

`any(k in text for k in keywords)`는 부분문자열 매칭이다. 3글자 이하 키워드
(`go·ai·llm·gpt·sql·api·sdk·cli·git·cve`)가 아무 영어 단어에나 걸린다.

```
통과 | She said the weather was nice today       → ['ai']   (s-ai-d)
통과 | A cat video went viral again              → ['ai']   (ag-ai-n)
통과 | Ago, a legitimate email chain about digits → ['go','ai','git']
```

실측: HN·lobsters 고유 제목 167건 중 **166건(99%)이 통과**. 칵테일 레시피, 등산기,
멜라토닌 연구, 솔리테어 게임이 전부 후보로 올라온다.

## 접근법

**단어경계만 적용하면 과차단된다** — 1차 시행에서 `containers`(복수형),
`released`(활용형)가 매치되지 않았고 `openai`·`github`·`copilot`은 애초에 어휘에 없어
`pg_clickhouse`, `Copilot MitM proxy`, `OpenAI head of ethics`까지 잘려나갔다.
그래서 세 가지를 함께 바꾼다.

1. **단어경계** — 앞뒤가 영숫자면 매치하지 않는다
2. **형태소 허용** — 4글자 이상은 `s/es/ed/ing/d`, 3글자 이하는 `s`만.
   짧은 키워드에까지 시제 어미를 허용하면 `going`(go+ing)·`aid`(ai+d)가 다시 샌다
3. **어휘 보강** — 50개 → 140개. `openai·anthropic·github·copilot·agentic·
   language·software·firmware` 등 1차 결과에서 오차단 근거가 나온 것만 추가

한국어에는 영향이 없다. 한글은 영숫자가 아니므로 경계 조건이 항상 성립한다.

## 단계별 계획

1. 테스트 작성(RED) — 부분문자열 오탐 차단 + 복수형·활용형 통과
2. `build.py`의 `keyword_filter()`를 정규식 기반으로 교체
3. `config.yaml`의 `keywords` 보강
4. 실데이터 재측정 → 개발 기사 오차단 없음 확인
5. verify → 커밋 → complete

## 완료 기준

- [ ] `said·again·ago·legitimate·digits`가 통과하지 않는다
- [ ] `containers·released·agents·APIs`가 통과한다
- [ ] 한국어 제목이 영향받지 않는다
- [ ] TRUSTED 출처는 여전히 필터를 우회한다
- [ ] 실데이터에서 통과율 99% → 77%, 차단 목록에 개발 기사가 없다
- [ ] 기존 테스트 전부 통과 + ruff 통과
- **완료일**: 2026-08-12T12:12:30.535Z
