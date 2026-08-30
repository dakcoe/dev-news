# EXEC_PLAN: drop-dead-category

- **타입**: chore
- **프로젝트**: project/dev-news
- **상태**: COMPLETED

## 목표

`scorer.py`가 모든 기사에 `category`를 붙이는데 **아무도 읽지 않는다.**
`news/template.html`·`news/render.py` 어디에도 참조가 없다(화면의 "카테고리"는
API 카탈로그용 별개 기능이다).

게다가 분포가 의미를 잃었다.

  trending 1033 · hot_debate 226 · multi_source 13   (1,272건 기준)

`multi_source`는 병합이 잡아 주기 전 제목 완전일치로만 세던 시절의 잔재고,
`hot_debate`는 댓글/업보트 비율 기준이라 그 지표가 없는 출처(rss·geeknews·
github)에는 원천적으로 붙을 수 없다.

**브라우저로도 나간다.** `docs/data/articles/*.json`에 실려 방문자마다
전송된다.

## 접근법

`scorer`에서 생산을 멈추고 저장분에서도 걷어낸다.

**`cross_source_count`는 남긴다.** 점수 가산(`* 300`)에 실제로 쓰이고
`dedup.merge_duplicates`가 채워 주는 값이다. 죽은 것은 `category`뿐이다.

저장분 정리는 `scripts/retag.py`가 이미 하는 일(전 기사 재작성 + 인덱스·docs
재생성)에 얹는다. 별도 스크립트를 늘리지 않는다.

## 단계별 계획

1. (RED) `tests/test_scorer_category.py` — category가 붙지 않을 것 ·
   cross_source_count는 유지될 것 · 점수 계산이 그대로일 것
2. `news/core/scorer.py` 정리
3. 저장분에서 필드 제거 + `retag.py`로 인덱스·docs 재생성
4. `node scripts/verify-task.js` → 커밋 → `complete-task.js`

## 완료 기준

- 새 기사에 `category`가 붙지 않는다
- 저장·배포 데이터에서 `category`가 사라진다
- `cross_source_count`와 점수 계산은 그대로다
- verify-task 통과

## 결과 (2026-08-31)

`scorer`에서 생산을 멈추고 저장·배포 데이터 1,272건에서 제거했다.
`retag.py`로 인덱스·docs를 재생성했다 — 기사 수는 1,272건 그대로다.

  배포 필드에서 category 사라짐 (잔존 0건)
  cross_source_count·score는 유지 — 점수 가산에 실제로 쓰인다

로컬 전체 실행 회귀 확인: 후보 240 → 142 → 미소개 95 → 선별 19로 이전과 동일.
- **완료일**: 2026-08-30T19:10:39.440Z
