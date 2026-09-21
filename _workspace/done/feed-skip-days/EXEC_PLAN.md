# EXEC_PLAN: feed-skip-days

- **타입**: fix
- **프로젝트**: project/dev-news
- **상태**: COMPLETED
- **완료일**: 2026-09-20

## 목표

피드가 `<skipDays>` 로 밝힌 휴재 요일의 0건을 침묵으로 세지 않는다.

## 왜

`add-source-silence-alert` 가 연속 N회차 0건인 출처를 죽은 것으로 보고
🟡 이슈를 연다. arXiv 는 주말에 `<item>` 이 하나도 없는 껍데기를 준다.
매주 토·일에 거짓 알람이 떴다.

`news/scrapers/rss.py` 주석은 "피드는 새 글이 없어도 기존 항목을 돌려주므로
0건은 곧 실패다" 라고 단정하고 있었다. arXiv 가 그 전제의 반례다.

## 접근법

- `rss.py` 의 `_skip_days(soup)` 가 RSS 2.0 `<skipDays>` 를 요일 번호로 읽는다.
- `fetch(..., skip_days=...)` 가 출처별로 채워 `build.py` 로 올린다.
- `source_health.record()` 가 회차 이력에 `skip` 을 같이 적는다.
- `silent()` 은 그 출처가 쉰다고 밝힌 요일의 회차를 **세지 않고 지나친다**.
  단순히 건너뛰면 streak 창이 짧아지므로, 셈에 든 회차가 streak 개 모일
  때까지 이력을 거슬러 올라간다.

## 되돌리지 말 것

**휴재 요일을 설정 파일에 손으로 적지 마라.** 피드가 스스로 선언한 값을 쓴다.
출처가 일정을 바꾸면 설정은 따라가지 않는다.
