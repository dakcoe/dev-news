# EXEC_PLAN: add-ad-slot

- **타입**: feat
- **프로젝트**: project/dev-news
- **상태**: COMPLETED

## 목표

뉴스 페이지에 광고 자리를 넣는다. 애드센스 승인 여부와 무관하게 **지금 바로
어떻게 보이는지 확인**할 수 있어야 하고, 승인 후에는 config 값만 채우면
그대로 실제 광고가 나가야 한다.

## 접근법

`config.yaml`의 `ads` 블록 하나로 제어한다. provider 두 가지:

| provider | 쓰임 |
|---|---|
| `placeholder` | 계정 없이 자리·레이아웃만 확인. 외부 스크립트를 전혀 부르지 않는다 |
| `adsense` | 실제 애드센스. client·slot 형식 검증을 통과해야만 켜진다 |

**형식이 틀리면 끈다(fail closed).** 잘못된 값을 그대로 head에 심으면 남의
스크립트를 페이지에 주입하는 통로가 된다 — `ca-pub-숫자` / 숫자 slot만 받는다.

**렌더 경로 주의.** `renderList()`가 검색 입력 한 글자마다 목록을 다시 그린다.
애드센스는 이미 채워진 `<ins>`를 다시 push하면 오류를 내므로,
`data-adsbygoogle-status`가 없는 것만 골라 push한다.

**위치는 피드 오른쪽 레일.** 처음에는 기사 사이(인피드)에 넣었으나 읽는 흐름을
끊어서 걷어냈다. 레일이 들어가는 만큼 컨테이너를 1180 → 1500px로 넓혀 피드 폭을
그대로 지키고, 1200px 미만 화면에서는 광고를 아예 그리지 않는다 — 좁은 화면에서
피드를 희생하면서까지 넣을 자리가 아니다.

## 단계별 계획

1. (RED) `tests/test_ads.py` — 꺼짐 기본값 · placeholder · adsense head 1회 ·
   잘못된 client/slot은 꺼짐 · 삽입 개수와 상한 · 값 이스케이프
2. `news/render.py`: `_ads_config()` 검증 + `__ADS_HEAD__` · `__ADS_JSON__` 치환
3. `news/template.html`: `.adrail`/`.adbox` 스타일 · `adHTML()` · `adRailHTML()` ·
   `body.ads` 클래스로 폭 확장 · `initAds()` 중복 push 방지
4. `config.yaml`에 `ads` 블록, `build.py`에서 전달
5. pytest → 커밋 → 아카이브

## 완료 기준

- `ads.enabled: false`면 결과 HTML에 광고 흔적이 전혀 없다
- `placeholder`로 켜면 외부 요청 없이 자리만 보인다
- `adsense`로 켜면 head 스크립트가 정확히 1개, 오른쪽 레일에 `<ins>`가 count만큼
- 기사 사이에는 광고가 들어가지 않는다
- 잘못된 client/slot은 광고를 끄고 로그를 남긴다
- 검색 중 목록이 다시 그려져도 광고가 중복 초기화되지 않는다
- pytest 전체 통과

## 결과

브라우저 확인(1568px): 오른쪽 레일에 sticky 광고 2개, 피드·패싯 사이드바 폭 유지,
콘솔 오류 없음. 기본값 `enabled: false`라 켜기 전까지 페이지는 지금과 동일하다.

- **완료일**: 2026-08-29
