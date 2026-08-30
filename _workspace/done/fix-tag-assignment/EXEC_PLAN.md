# EXEC_PLAN: fix-tag-assignment

- **타입**: fix
- **프로젝트**: project/dev-news
- **상태**: COMPLETED

## 목표

태그가 필터 UI에 직접 노출되는데 근거 없는 것이 흔하다. 기사당 평균 3.83개 중
1~2개가 오배정이다.

  padding-bottom aspect-ratio (CSS)  → security, web        ← security 무관
  Delta encoding multiplayer game    → release, science      ← 둘 다 무관
  checkstyle (Java 린터)             → web, career-culture   ← 둘 다 무관

`ai`는 1,272건 중 대부분에 붙어 필터로서 변별력이 없다.

## 원인 (실측으로 특정)

**오배정의 대부분이 `요약`에서 나온다.** 태거는 `제목+ko_title+설명+요약`에
정규식을 돌리는데, 요약은 LLM이 쓴 부연이라 본문 주제와 먼 단어가 흔하다.

  Delta encoding … 요약의 "은하"(게임 세계관) → science
                   요약의 "업데이트"          → release
  checkstyle …     요약의 "html"(문서 형식)   → web
                   설명의 "programmer"        → career-culture

단독으로 태그를 만든 패턴을 세어 보니 상위가 전부 **범용 한국어 명사**였다:

  공개 114 · 도구 136 · 연구 68 · 웹 62 · 배포 58 · 서버 53 · 평가 48
  안전 37 · 기업 33 · 커뮤니티 33 · 발표 32 · 업데이트 32

이런 말은 어떤 기사의 요약에도 스치듯 등장한다.

## 접근법

**요약을 통째로 빼는 안은 폐기했다.** 실측으로 재보니 123건이 태그 0개가 되고
정당한 `llm` 태그 140건도 사라진다(제목이 짧아 요약에만 근거가 있는 경우).

대신 패턴을 두 갈래로 나눈다.

| 갈래 | 예 | 검사 범위 |
|------|-----|-----------|
| 강함 (고유명사·전문용어) | `openai` `claude` `\bcss\b` `kubernetes` | 제목+설명+요약 전부 |
| 약함 (범용어) | `공개` `도구` `연구` `서버` `기업` | **제목 + ko_title만** |

스치듯 나온 범용어로는 태그가 붙지 않고, 제목에 있으면 그 기사의 주제이므로
인정한다. 설명·요약에서도 고유명사는 그대로 잡힌다.

**`hack` 단독 매칭 제거.** `hack(ed|ing|er)?`의 `?` 때문에 "Aspect-Ratio Hack"의
"요령"이 security가 됐다. 접미사를 필수로 바꿔 `hacked|hacking|hacker`만 잡는다.

**MAX_TAGS 6 → 4.** 필터 UI에서 태그가 많을수록 변별력이 떨어진다.

## 단계별 계획

1. (RED) `tests/test_tag_precision.py` — 실측 오배정 4건이 사라질 것 ·
   정당한 태그는 유지될 것 · 약한 패턴이 제목에 있으면 인정 · hack 접미사
2. `news/core/tags.py` — `WEAK_PATTERNS` 도입, `tag_article` 2단 매칭,
   `hack` 패턴 수정, `MAX_TAGS` 조정
3. 8월 전체 1,272건 회귀 — 태그 0개 기사 수·평균 태그 수 확인
4. `node scripts/verify-task.js project/dev-news`
5. 커밋 → `complete-task.js`

## 완료 기준

- 실측 오배정 4건에서 무관한 태그가 사라진다
- 태그가 0개가 되는 기사가 크게 늘지 않는다 (요약 제외 안의 123건보다 훨씬 적을 것)
- 기사당 평균 태그가 줄어든다
- verify-task 통과

## 결과 (2026-08-31)

강한/약한 패턴 2단 매칭. 약한 패턴(범용어 43개)은 **출처가 준 원제목에서만**
인정하고, 강한 패턴(고유명사·전문용어)은 제목+설명+요약 전부에서 잡는다.

**검사 범위를 ko_title까지 좁힌 것이 결정적이었다.** 처음에는 약한 패턴을
"제목 + ko_title"에 걸었는데 두 사례가 남았다:

  "Aspect-Ratio Hack" → ko_title "비율 해킹"(오역)  → security
  요약의 "HTML 형식의 문서를 지원"                   → web

둘 다 **LLM이 만든 글에서만** 나온 근거였다. ko_title·summary는 원문에 없는
말이 섞이므로, 약한 패턴은 출처가 준 `title`만 본다.

`hack(ed|ing|er)?`의 `?`도 제거했다 — "요령"을 뜻하는 hack이 보안이 됐다.

**8월 전체 1,272건 회귀**

  기사당 평균 태그   3.83 → 2.80
  태그 0개 기사       33 → 63 (4.9%, 기준 5% 이내)
  ai 태그 보유       864 → 856

  Delete Your padding-bottom …  [security, web] → [web]
  Delta encoding multiplayer …  [web, backend-data, release, science] → [web]
  checkstyle / checkstyle       [dev-tools, web, language, open-source,
                                 release, career-culture]
                              → [language, open-source, release]

요약을 통째로 빼는 안은 실측으로 폐기했다 — 태그 0개가 123건이 되고 정당한
llm 태그 140건이 사라졌다.

`scripts/retag.py`로 기존 코퍼스에 소급 반영했다 (SPEC 1B가 명시한 절차).

**기존 테스트 기준 갱신.** `tests/test_tags.py:test_corpus_distribution`이
이전 작업(add-article-tags)의 완료 기준인 평균 3.0~4.5를 고정하고 있어
2.5~3.5로 바꿨다 — 개수가 준 것이 아니라 근거 없는 태그가 빠진 것이다.

**남긴 것.** `ai` 태그는 여전히 856/1,272(67%)다. `\bai\b`·`openai`·`anthropic`은
강한 패턴이고 실제로 AI 기사가 많은 피드라, 억지로 낮추지 않았다.
- **완료일**: 2026-08-30T18:14:07.199Z
