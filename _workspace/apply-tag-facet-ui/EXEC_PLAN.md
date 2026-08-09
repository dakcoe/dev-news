# EXEC_PLAN: apply-tag-facet-ui

- **타입**: feat
- **프로젝트**: project/dev-news
- **상태**: IN_PROGRESS
- **생성일**: 2026-08-09T04:21:01.570Z

## 목표

태그 필터 UI를 시안 F+I 반응형 조합으로 교체 (사용자 확정):
데스크톱 = 분포 막대 그룹 패싯 사이드바, 좁은 화면 = 슬라이드 드로어.
기존 태그 칩 한 줄(tagchips)은 제거, 단일 선택 → 다중 선택(OR)으로 전환.

## 접근법

- tags.py VOCAB에 group 필드 추가 (AI / 개발 / 그 외) → render.py가 __TAG_JSON__으로
  {id: {label, group}} 전달. 어휘·그룹 정의는 파이썬 한 곳에만 둔다.
- template.html:
  - 상태: tagFilter(단일) → tagSel(Set, localStorage 'dev-news-tagsel' JSON 배열, SPEC 3.3).
    구 키(dev-news-tagfilter)는 최초 로드 시 Set으로 승격 마이그레이션.
  - facetHTML(): 그룹 헤더 + 체크박스 행 + 기사 수 비례 분포 막대(현재 기간 범위 기준).
    같은 마크업을 데스크톱 사이드바와 모바일 드로어가 공유 — CSS 미디어쿼리로만 전환.
  - 레이아웃: 기사 목록을 .layout(사이드바+피드 flex)으로 감싼다. ≤900px에서 사이드바가
    fixed 드로어로 바뀌고 바에 "태그 N" 버튼 노출. 스크림 클릭·닫기로 복귀.
  - 행의 태그 칩 클릭 = 선택에 추가(토글). 검색은 다중 선택과 AND로 동작.
- 회귀: 보관함·읽음·아카이브 검색·`--demo` 유지. sample.json(태그 없음)에서도
  사이드바가 0건 카운트로 정상 렌더.

## 단계별 계획

1. RED: test_template.py에 패싯 회귀 테스트 추가 (facet 존재, tagchips 제거, 드로어 버튼,
   다중 선택 상태 키) + render.py TAG_JSON group 포함 테스트
2. tags.py group 추가 → render.py TAG_JSON 확장
3. template.html CSS/JS 구현
4. --demo 별도 경로 렌더로 육안 확인 요소 검증 → retag.py로 실데이터 재렌더·docs 동기화
5. verify-task.js → 커밋 → 완료 처리

## 완료 기준

- [ ] 신규 테스트 포함 pytest 전체 통과, ruff 통과
- [ ] 데스크톱: 그룹·분포막대·다중선택 사이드바 / 좁은 화면: 드로어 + 태그 버튼
- [ ] 태그 다중 선택(OR)이 localStorage에 저장·복원, 구 단일 키 마이그레이션
- [ ] docs/index.html 재렌더·동기화 완료, 기존 기능 회귀 없음
