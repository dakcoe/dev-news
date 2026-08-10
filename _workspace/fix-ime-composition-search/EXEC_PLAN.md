# EXEC_PLAN: fix-ime-composition-search

- **타입**: fix
- **프로젝트**: project/dev-news
- **상태**: IN_PROGRESS

## 목표

맥 한글 IME로 검색창에 입력하면 자모가 낱개로 들어가는(ㄱㅏㄴㅏ) 문제 수정.
원인: oninput마다 render()가 뷰 전체를 재생성해 input이 교체되면서 IME 조합 세션이 끊김.

## 접근법

조합 중에는 재렌더를 건너뛰고(e.isComposing), compositionend에서 한 번만 렌더.
Chrome(조합 중 input.isComposing=true → compositionend)과 Safari(compositionend 후
최종 input 발화) 이벤트 순서 차이를 두 핸들러 조합으로 모두 커버.
덤으로 커서를 항상 끝으로 보내던 것을 원래 위치 보존으로 개선.

## 단계별 계획

1. RED: 템플릿에 compositionend 처리·isComposing 가드가 있어야 한다는 테스트
2. GREEN: bind()의 검색 입력 핸들러 수정
3. retag로 docs 재생성 → verify → 커밋 → complete → push

## 완료 기준

- 조합 가드(compositionend + isComposing) 존재를 테스트로 고정, 전체 테스트 통과
