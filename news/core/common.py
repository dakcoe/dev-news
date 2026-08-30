"""여러 모듈이 함께 쓰는 상수와 유틸 (consolidate-shared-utils).

여기 모으기 전에는 같은 코드의 사본이 흩어져 있었고 서로 조금씩 달랐다.
날짜 파싱은 geeknews·rss·lobsters·reddit·scorer가 각자 구현했는데, rss만
tzinfo 없는 값을 UTC로 보정하고 geeknews는 하지 않았다. naive datetime에
.astimezone()을 부르면 파이썬이 로컬 시각으로 해석하므로, 같은 피드가
로컬(KST)과 Actions(UTC)에서 9시간 다른 값으로 저장됐다.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

KST = timezone(timedelta(hours=9))

# news/core/common.py → news/core → news → 프로젝트 루트
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def to_timestamp(value) -> float | None:
    """날짜 문자열이나 epoch 숫자를 UTC 타임스탬프(float)로.

    RFC 2822("Wed, 20 Aug 2026 12:00:00 +0000"), ISO 8601(Z 접미사 포함),
    epoch 숫자를 받는다. 형식을 못 알아보면 None.

    **타임존이 없는 값은 UTC로 본다.** 로컬 시각으로 해석하면 실행 환경에 따라
    결과가 달라진다 — 이 프로젝트에서 실제로 겪은 버그다.
    """
    if value is None or isinstance(value, (list, dict, tuple, set)):
        return None

    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return None

    # epoch 숫자가 문자열로 오는 경우
    try:
        return float(text)
    except ValueError:
        pass

    for parse in (parsedate_to_datetime,
                  lambda v: datetime.fromisoformat(v.replace("Z", "+00:00"))):
        try:
            dt = parse(text)
        except Exception:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    return None
