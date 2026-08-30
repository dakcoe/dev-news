# EXEC_PLAN: block-dead-links

- **타입**: fix
- **프로젝트**: project/dev-news
- **상태**: COMPLETED

## 목표

이미 사라진 링크가 그대로 페이지에 실린다. 최신 250건 실측에서 3건:

  HTTP 404  https://news.hada.io/topic?id=32193
  HTTP 404  https://dev.to/linxian/i-built-a-chinese-neighborhood-auntie-...
  HTTP 503  https://web.archive.org/web/.../github.com/ancaferro/myNetwork/pull/3

독자가 눌러도 아무것도 없는 링크다. 잘못된 정보를 내보내는 문제라 우선순위가 높다.

## 원인

`news/core/enrich.py:_fetch_one`이 `raise_for_status()`로 404와 일시적 오류를
똑같이 삼켜 `(None, None)`을 돌려준다. 상태 코드가 파이프라인 밖으로 나오지
않으니 게재 여부를 판단할 재료 자체가 없다.

  except requests.RequestException:
      return None, None          # ← 404인지 502인지 구분이 사라진다

## 접근법

**판정표를 새로 만들지 않는다.** `news/api_health.py:classify()`가 이미 같은
문제를 풀어 놨고 실측으로 다듬어진 규칙이다. 그대로 재사용한다.

| 판정 | 근거 | 기사 처리 |
|------|------|-----------|
| dead | 404·410, DNS 실패·연결 거부 | 게재 제외 |
| unknown | 5xx, 타임아웃 | 게재 (일시 장애일 수 있다) |
| ok | 2xx·3xx, 401/403/429 등 | 게재 |

**403을 죽음으로 세지 않는 것이 핵심이다.** 실측 403 4건(economist·stanford·
oup·axios)은 전부 살아 있는 페이지이고 봇 차단일 뿐이다. 여기서 뺐다가는
멀쩡한 기사를 잃는다. 위 표의 `unknown`도 같은 이유로 남긴다 — 503이 났던
web.archive.org 건은 일시 장애였을 수 있다.

**enrich 직후, 요약 전에 뺀다.** 죽은 링크에 LLM 호출을 쓰지 않게 된다.

**제외분은 seen에 넣는다.** 안 그러면 다음 회차에 다시 후보로 올라와 같은
URL을 매번 다시 두드린다 (llm-relevance-gate에서 쓴 방식과 같다).

**GitHub README 경로는 판정 대상이 아니다.** `_fetch_one`은 github.com 링크를
raw README로 우회하는데, README가 없어 404가 나도 저장소는 멀쩡하다.

## 단계별 계획

1. (RED) `tests/test_dead_links.py` — 404·410 제외 · 403·429 유지 ·
   5xx·타임아웃 유지 · DNS 실패 제외 · github 경로 예외 · 판정 없으면 유지
2. `news/core/enrich.py` — `raise_for_status()` 제거, 상태를 `link_status`로 반환
3. `build.py` — `drop_dead_links()` 추가, enrich 직후 적용, 제외분 seen 등록
4. `node scripts/verify-task.js project/dev-news`
5. 커밋 → `node scripts/complete-task.js`

## 완료 기준

- 404·410 링크가 페이지에 실리지 않는다
- 403·429·5xx·타임아웃은 그대로 실린다 (오탐 방지)
- GitHub 저장소 링크가 README 부재로 빠지지 않는다
- 제외분이 seen에 남아 다음 회차에 재확인되지 않는다
- verify-task 통과 (테스트 + 린트)
- **완료일**: 2026-08-30T18:06:55.168Z
