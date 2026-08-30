# EXEC_PLAN: show-feeds-in-sources

- **타입**: feat
- **프로젝트**: project/dev-news
- **상태**: COMPLETED

## 목표

페이지의 "수집 소스" 화면에 개별 RSS 피드가 보이지 않는다. Hugging Face가
수집·게재되고 있는데도(8월 21건) 화면에서는 찾을 수 없다.

## 원인

소스 화면은 `news/render.py`의 `SOURCE_META` 8개만 그린다. 피드 7개가
`블로그 · RSS` 하나로 뭉뚱그려져 있다.

  "rss": {"name": "블로그 · RSS",
          "desc": "config.yaml의 feeds 목록 — 공식 블로그와 기술 매체"}

실제 기여는 작지 않다 — 8월 1,292건 중 288건(22%)이 이 경로다.

  The Decoder 158 · Simon Willison 62 · OpenAI 26 · Hugging Face 21
  Google AI Blog 9 · 토스 8 · 카카오 2

## 접근법

**뷰 모델은 손대지 않는다.** `to_view_model`이 이미 `from`에 피드 이름을
채우고 있다(RSS는 피드명, 레딧은 r/이름). 템플릿에서 그걸로 묶으면 된다.

소스 카드 아래에 하위 목록을 단다. 특정 소스를 하드코딩하지 않고 **`from`
값이 여러 개인 소스면 자동으로** 펼친다 — `rss`뿐 아니라 `anthropic`
(news / engineering)에도 자연스럽게 적용되고, 나중에 피드를 추가해도
코드를 고칠 필요가 없다. `rss.py`의 "주소만 추가하면 소스가 늘어난다"는
설계 의도와 맞다.

건수는 **누적**이 아니라 화면에 실린 기간(`keep_days: 30`) 기준으로 센다 —
소스 카드의 기존 "최근 N건"과 같은 기준이라야 숫자가 어긋나지 않는다.

## 단계별 계획

1. (RED) `tests/test_source_feeds.py` — 피드 하위 목록이 그려질 것 ·
   피드명이 들어갈 것 · 단일 출처는 펼치지 않을 것
2. `news/template.html`의 `view==='src'` 블록 수정
3. 렌더 결과 육안 확인
4. `node scripts/verify-task.js` → 커밋 → `complete-task.js`

## 완료 기준

- 수집 소스 화면에서 Hugging Face 등 개별 피드가 보인다
- 피드별 건수가 소스 카드의 "최근 N건"과 같은 기준이다
- 피드가 하나뿐인 소스(hackernews 등)에는 하위 목록이 붙지 않는다
- verify-task 통과
- **완료일**: 2026-08-30T20:04:41.792Z

## 결과 (2026-08-31)

소스 카드 아래에 피드 하위 목록을 단다. 렌더 확인:

  블로그 · RSS   최근 288건
    The Decoder 158 · Simon Willison 62 · OpenAI 26 · Hugging Face 21
    Google AI Blog 9 · 토스 8 · 카카오 2 · r/LocalLLaMA 2

  Anthropic     최근 10건
    Anthropic 9 · Anthropic Engineering 1

**특정 출처를 하드코딩하지 않은 것이 값을 했다.** `from` 값이 여럿인 출처면
자동으로 펼치게 했더니 Anthropic의 news/engineering 구분도 공짜로 따라왔다.
피드가 하나뿐인 출처(Hacker News·GitHub 등)에는 하위 목록이 붙지 않는다.

건수는 소스 카드의 "최근 N건"과 같은 기준(화면에 실린 keep_days 범위)이라
숫자가 어긋나지 않는다.

**작업 중 실수 하나.** CSS에 없는 변수(`--bg2`·`--tx1`)를 썼다가 정의된
이름(`--line2`·`--tx`)으로 고쳤다. 테스트는 통과했지만 브라우저로 실제 화면을
보지 않았으면 색이 빠진 채 나갔을 것이다.
