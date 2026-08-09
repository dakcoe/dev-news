# EXEC_PLAN: facet-collapse-toggle

- **타입**: feat
- **프로젝트**: project/dev-news
- **상태**: IN_PROGRESS
- **생성일**: 2026-08-09T05:54:22.056Z

## 목표

데스크톱 태그 패싯 사이드바를 접고 펼 수 있게 한다 (사용자 요청).
접으면 피드가 전체 폭을 쓰고, 접힘 상태는 localStorage로 유지된다.

## 접근법

- 상태 `facetCollapsed` + localStorage 'dev-news-facetfold'.
- 패싯 상단에 헤더("태그" + 접기 버튼) 추가. 접기 버튼은 데스크톱에서만 표시
  (모바일 드로어는 스크림 클릭으로 닫는 기존 방식 유지).
- 접힘 시: 데스크톱에서 .layout.fc가 사이드바를 숨기고, 기존 "태그 N" 버튼이
  데스크톱에도 노출(#tagbtn.show)돼 다시 펼치는 입구가 된다.
- tagbtn 클릭 분기: 좁은 화면(matchMedia ≤900px) = 드로어 열기 / 데스크톱 = 펼치기.

## 단계별 계획

1. RED: 접기 버튼·저장 키·fc 클래스 존재 테스트 추가
2. template.html 구현 (CSS + facetHTML 헤더 + bind 분기)
3. retag.py 재렌더 → 브라우저에서 접기/펼치기·새로고침 유지 확인
4. verify-task.js → 커밋 → 완료 처리

## 완료 기준

- [ ] pytest 전체·ruff 통과
- [ ] 접기 → 피드 전폭, "태그" 버튼으로 펼침, 새로고침 후에도 접힘 유지
- [ ] 모바일 드로어 동작 회귀 없음
