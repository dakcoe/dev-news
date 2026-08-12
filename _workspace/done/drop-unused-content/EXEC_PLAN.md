# EXEC_PLAN: drop-unused-content

- **타입**: fix
- **프로젝트**: project/dev-news
- **상태**: COMPLETED

## 목표

화면에 한 번도 쓰이지 않는 수집 원문(`content`)을 저장하지 않는다. 저장소 용량,
페이지 전송량, 시크릿 노출면을 한꺼번에 줄인다.

## 배경 — 측정

`content`는 요약 생성의 입력일 뿐 렌더에는 쓰이지 않는다. `template.html`이 실제로
읽는 필드는 `description·image·ko_title·summary·tags·why`뿐이다.

| 항목 | 값 |
|------|-----|
| `data/articles/2026-08.json` | 1.59 MB (353건) |
| 그중 `content` | 817K자 = **66%** |
| 사본 | `data/`와 `docs/data/`에 **바이트 동일하게 2벌** |
| 사용자 영향 | 아카이브 검색 시 1.59MB 다운로드 (그중 2/3이 안 쓰는 원문) |

시크릿 노출면이기도 하다 — fix-secret-push-block이 막은 HF·AWS·GitHub 토큰 4건은
전부 `content` 안에 있었다. 저장하지 않으면 그 경로 자체가 사라진다(2차 방어선).

## 접근법

`content`는 enrich → summarizer 구간에서만 살아 있으면 된다. 아카이브에 넣기 직전에
떼어낸다. 파이프라인 중간을 건드리지 않으므로 요약 품질에는 영향이 없다.

`news/core/archive.py`의 `append()`에서 떼는 게 맞다 — 저장 계층의 책임이고,
`docs/` 사본은 `sync_docs_data()`가 아카이브를 그대로 복사하므로 자동으로 따라온다.

기존에 쌓인 원문은 일회성 정리 스크립트로 제거한다. 이번 달 샤드는 가변이라
"지난 달 샤드 불변" 원칙에 걸리지 않는다.

## 단계별 계획

1. 테스트 작성(RED) — `append()`가 `content`를 저장하지 않고 나머지는 보존
2. `archive.py`에 `DROP_FIELDS` 적용
3. `scripts/purge_content.py` — 기존 샤드 일회성 정리
4. 실행 후 용량 재측정, `sync_docs_data()`로 docs 갱신
5. verify → 커밋 → complete

## 완료 기준

- [ ] `append()`가 저장한 기사에 `content` 키가 없다
- [ ] `summary·why·ko_title·tags·image·description`은 그대로 보존된다
- [ ] 요약 파이프라인은 여전히 `content`를 재료로 쓴다 (enrich→summarizer 무영향)
- [ ] 기존 샤드에서 `content` 제거 후 용량 60% 이상 감소
- [ ] 기존 테스트 전부 통과 + ruff 통과
- **완료일**: 2026-08-12T12:14:19.601Z
