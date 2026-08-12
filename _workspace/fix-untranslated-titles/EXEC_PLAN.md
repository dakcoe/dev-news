# EXEC_PLAN: fix-untranslated-titles

- **타입**: fix
- **프로젝트**: project/dev-news
- **상태**: IN_PROGRESS

## 목표

영어 제목이 번역되지 않고 그대로 남는 문제를 고친다. 방금 만든 채점기가 잡은
첫 결함이다.

## 배경 — 채점기가 잡은 것

`scripts/eval_summary.py` 기준선(gpt-oss-120b, 12건): 무결점 83%, `untranslated` 83%.

```
- [untranslated] datasette-upload-dbs 0.5a0
- [untranslated] React useEventSource Hook: Server-Sent Events with Auto-Reco
```

두 사례의 성격이 다르다.

- **`React useEventSource Hook: …`** — 평범한 영어 문장 제목이다. 번역했어야 한다.
- **`datasette-upload-dbs 0.5a0`** — 패키지명 + 버전이다. 번역할 게 없다.
  이건 옮기는 게 아니라 **한국어 설명을 붙여야** 한다.

## 원인

프롬프트가 설명 붙이기를 **GitHub 저장소에만** 지시하고 있다.

> 번역제목: (제목이 외국어면 자연스러운 한국어로. 이미 한국어면 그대로.
> GitHub 저장소면 "owner / repo — 한 줄 설명" 형태)

패키지명·제품명·버전 문자열은 "외국어"도 "GitHub 저장소"도 아니어서 규칙의
사각지대에 있다. 모델이 원제를 그대로 복사하는 게 지시를 어긴 게 아니다.

llama 시절 산출물에는 `datasette-upload-dbs 0.5a0 — Datasette 인스턴스에 SQLite
데이터베이스 업로드 플러그인` 형태가 실제로 있었다. 원하는 형태가 이미 나온 적이
있으므로 프롬프트만 정확히 지시하면 된다.

## 접근법

규칙을 저장소 한정에서 **"고유명사라 옮길 수 없는 제목 일반"**으로 넓힌다.
번역할 수 있는 문장은 번역하고, 옮길 수 없는 이름은 뒤에 한국어 설명을 붙인다.

프롬프트만 고친다. 채점기·모델·파이프라인은 건드리지 않는다. 효과는 같은 골든
코퍼스로 전후 비교해서 수치로 확인한다 — 이게 채점기를 만든 이유다.

## 단계별 계획

1. `summarizer.py`의 `PROMPT` 번역제목 규칙 수정
2. 골든 코퍼스로 재채점 — `untranslated` 개선 확인
3. 개선됐으면 기준선 갱신
4. verify → 커밋 → complete

## 완료 기준

- [ ] `untranslated` 통과율이 기준선(83%)보다 오른다
- [ ] 다른 지표가 내려가지 않는다 (특히 `length`·`residue`)
- [ ] 한국어 원제는 여전히 그대로 유지된다
- [ ] 기준선 파일이 갱신된다
- [ ] 기존 테스트 전부 통과 + ruff 통과
