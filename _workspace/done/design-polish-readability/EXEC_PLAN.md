# EXEC_PLAN: design-polish-readability

- **상태:** IN_PROGRESS
- **유형:** feat
- **생성:** 2026-09-02

## 목표
Work/design 레퍼런스(design-specimen-ledger.html)를 근거로 뉴스 페이지의
읽기 편의성을 높이는 절제된 디자인 다듬기.

## 접근법 (레퍼런스 근거)
1. SF-01 Beautiful Shadows — .row/.scard 카드의 1px 보더를 다단 레이어 그림자로 교체
2. RF Typeset — 기사 제목 위계 강화, 상세뷰 첫 문단 리드(lede) 처리
3. RF Layout — 날짜 그룹 간 여백 확대, 스니펫 줄 길이 70ch 제한
4. Diff Ledger(AI 슬롭) 지양 — 사이드탭 보더·아이브로우 칩·중첩 카드·퍼플블루 그라디언트 금지

## 단계별 계획
1. RED — tests/test_design_polish.py (그림자 토큰 존재, 카드 보더 제거 확인)
2. GREEN — template.html CSS 수정
3. 재렌더 + 로컬 Chrome으로 데스크톱/모바일 확인
4. verify-task.js → 커밋 → 푸시

## 완료 기준
- 카드가 보더 없이 레이어 그림자로 구분됨, 호버 시 자연스러운 부상
- 제목/스니펫 위계가 이전보다 뚜렷, 스니펫 장행 제한
- 기존 기능(선택 상태 .act, 읽음 .rd, 광고 레일) 회귀 없음
- pytest + ruff 통과

- **상태**: COMPLETED
- **완료일**: 2026-09-02T04:03:14.151Z
