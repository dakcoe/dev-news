"""여러 모듈이 함께 쓰는 상수와 유틸 (consolidate-shared-utils).

여기 모으기 전에는 같은 코드의 사본이 흩어져 있었고 서로 조금씩 달랐다.
날짜 파싱은 geeknews·rss·lobsters·reddit·scorer가 각자 구현했는데, rss만
tzinfo 없는 값을 UTC로 보정하고 geeknews는 하지 않았다. naive datetime에
.astimezone()을 부르면 파이썬이 로컬 시각으로 해석하므로, 같은 피드가
로컬(KST)과 Actions(UTC)에서 9시간 다른 값으로 저장됐다.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

KST = timezone(timedelta(hours=9))

# news/core/common.py → news/core → news → 프로젝트 루트
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class DataUnreadable(RuntimeError):
    """있는 파일을 못 읽었다. 그 위에 덮어쓰면 남아 있던 것까지 잃는다."""


def load_json(path: str, default):
    """없으면 default, 있는데 못 읽으면 DataUnreadable.

    이 저장소의 누적 파일은 거의 다 같은 모양이다 — 읽어서 오늘 것을 얹고
    같은 경로에 다시 쓴다(seen·candidates·archive·source_health). 읽기 실패를
    빈 값으로 돌려주면 그 한 번으로 누적분이 통째로 지워지고, 그게 그대로
    커밋·푸시된다. 파일이 남아 있는 한 되살릴 수 있으니 회차를 멈추는 쪽이 맞다.

    default 는 빈 list 나 dict 다. 그 종류와 다른 JSON 이 들어 있어도 예외다 —
    옛 형식이 남아 있는데 빈 값으로 갈아 끼우면 같은 손실이 난다.
    """
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        raise DataUnreadable(f"{path}: {e}") from e
    if type(data) is not type(default):
        raise DataUnreadable(
            f"{path}: {type(default).__name__} 이 아니라 {type(data).__name__}")
    return data


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
