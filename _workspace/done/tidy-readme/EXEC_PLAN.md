# EXEC_PLAN: tidy-readme

- **타입**: docs
- **프로젝트**: project/dev-news
- **상태**: COMPLETED

## 목표

README를 현재 코드(SPEC Phase 1~3 반영 이후)와 맞게 정리한다.

## 접근법

코드·config.yaml·template.html·workflow를 대조해 어긋난 서술을 고치고, 빠진 기능(태그·아카이브·무료 API 목록)을 추가한다. 구조는 유지.

## 단계별 계획

1. 어긋난 부분 목록화: data/articles.json → 월별 샤드, max_items 폐기, 점수순 정렬·HOT·NEW 배지 제거, 기본 모델 gpt-oss-120b, Python 3.12, Reddit OAuth 발급 막힘
2. 누락 기능 추가: 태그(닫힌 어휘·retag), 아카이브 검색, 무료 API 목록, LLM 호출 예산, page:false 피드, long_window, 게시 부족 알림
3. 잡담성 문구(zip 배포 노트, 디스코드 비유) 제거

## 완료 기준

- README의 모든 파일 경로·플래그·설정 키가 실제 코드에 존재
- 기존 테스트 통과 (코드 변경 없음)
- **완료일**: 2026-09-02T12:41:08.625Z
