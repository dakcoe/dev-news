# EXEC_PLAN: account-deletion

- **타입**: feat
- **프로젝트**: project/dev-news
- **상태**: COMPLETED
- **완료일**: 2026-09-20

## 목표

로그인한 사람이 자기 계정과 저장된 기록을 직접 지운다.

## 왜

`sync-across-devices` 로 보관함·읽음 표시가 서버에 남기 시작했다. 지우는
방법이 없으면 사람들에게 권할 수 없다.

## 접근법

```
worker/src/index.js   POST /account/prepare  ·  DELETE /account
news/template.html    프로필 아이콘 팝업(로그아웃 · 탈퇴) + 소개 화면 하단
```

**2단계다.** `/account/prepare` 가 일회용 nonce 를 만들어 세션 행과 쿠키에
같이 넣고, `DELETE /account` 는 그 둘이 맞을 때만 지운다. 한 번의 왕복으로
끝나면 남의 화면에 심은 링크가 계정을 지울 수 있다 — 깃허브 승인이 살아
있으면 클릭 한 번이면 된다. `SameSite=Lax` 라 다른 사이트에서 온 POST 에는
쿠키가 실리지 않으므로 1단계는 우리 화면에서만 성공한다.

## 되돌리지 말 것

**지운 뒤 `syncEpoch` 를 올려라.** 안 올리면 이미 날아간 `syncFlush()` 의
응답이 돌아와 지워진 계정을 로그인 상태로 되돌린다.

**지운 뒤 로컬 사본까지 비운다.** 안 비우면 다음 로그인 때 그 기록이 새
계정으로 다시 올라간다.

**탈퇴 직후 `render()` 를 바로 부르지 마라.** 스크립트 로드 중에 부르면
`Cannot access 'I' before initialization` 으로 화면이 깨진다. `setTimeout(…, 0)`
으로 미룬다.
