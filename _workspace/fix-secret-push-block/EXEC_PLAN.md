# EXEC_PLAN: fix-secret-push-block

- **타입**: fix
- **프로젝트**: project/dev-news
- **상태**: IN_PROGRESS
- **생성일**: 2026-08-11T16:55:54.743Z

## 목표

수집한 기사 본문에 섞여 들어온 남의 API 토큰 때문에 GitHub Push Protection이 push를
거부해 워크플로우가 실패하는 문제를 없앤다. 파이프라인이 디스크에 쓰는 모든 텍스트에서
시크릿 패턴을 마스킹해, 어떤 기사를 수집하든 push가 막히지 않게 한다.

## 배경 — 실패 원인

run 31510062957 (2026-08-12 01:02 KST) `변경분 커밋` 스텝:

```
remote: - GITHUB PUSH PROTECTION
remote:   —— Hugging Face User Access Token ——
remote:      path: docs/data/articles/2026-08.json:311
 ! [remote rejected] main -> main (push declined due to repository rule violations)
```

`news/core/enrich.py`가 기사 본문(웹 본문 · GitHub README)을 원문 그대로 `content`에
담고, 그게 `data/articles/YYYY-MM.json` → `docs/data/articles/`로 커밋된다. 이번 회차
본문 중 하나에 `hf_…` 형태의 Hugging Face 액세스 토큰이 박혀 있어 차단됐다.
`data/candidates/YYYY-MM.json`의 `title`·`description`도 같은 경로로 노출된다.

dev-news 자신의 키가 유출된 게 아니라 **남의 토큰을 그대로 퍼와 커밋하려다 막힌 것**이다.
unblock URL로 허용 처리하는 건 남의 진짜 토큰을 공개 저장소에 박는 셈이라 채택하지 않는다.

## 접근법

`news/core/redact.py` 신설 — GitHub 시크릿 스캐닝이 탐지하는 주요 공급자 토큰 패턴을
정규식으로 잡아 `[REDACTED]`로 치환한다. 기사 dict의 모든 문자열 값을 재귀적으로 훑는다.

`build.py` 파이프라인 3지점에 삽입한다. 한 곳이 아닌 이유:

1. `dedupe()` 직후 — `candidates.log()`가 쓰는 title·description을 보호
2. `enrich()` 직후 — 본문을 보호하고, **요약 요청으로 남의 토큰이 LLM 공급자에게
   전송되는 것까지 막는다**
3. 요약 직후 — LLM이 본문의 토큰을 요약문에 되뱉는 경우를 막는다

차단 필터가 아니라 마스킹이다. 기사 자체는 그대로 게시되고 토큰 문자열만 가려진다
(SPEC 1.1 "파이프라인 수준 차단 필터를 두지 않는다"와 충돌하지 않음).

## 단계별 계획

1. `tests/test_redact.py` 작성 — 실패 재현(RED): HF 토큰이 든 본문이 아카이브에
   원문 그대로 저장되지 않아야 한다
2. `news/core/redact.py` 구현(GREEN) — `redact_text()`, `redact_articles()`
3. `build.py`에 3지점 삽입
4. `node scripts/verify-task.js project/dev-news` 통과
5. 커밋 → `complete-task.js`

## 완료 기준

- [ ] `tests/test_redact.py` — HF/Anthropic/OpenAI/GitHub/AWS/Google/Slack/Groq/
      OpenRouter/개인키 패턴이 모두 마스킹됨
- [ ] 정상 텍스트(한글 본문, 일반 URL, 코드 블록)는 손상되지 않음 — 오탐 회귀 테스트
- [ ] 중첩 구조(list·dict)와 비문자열 값(int·bool·None)이 보존됨
- [ ] `build.py` 파이프라인을 통과한 기사가 아카이브·candidates 어디에도 원문 토큰을
      남기지 않음
- [ ] 기존 테스트 전부 통과 + ruff 린트 통과
