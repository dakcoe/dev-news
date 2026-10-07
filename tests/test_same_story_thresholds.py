"""같은 사건 거르기 기준값(similar.AUTO·JUDGE)이 판정 자료와 맞는지 지킨다.

흐름 테스트(test_similar.py)는 기준값 구간의 한가운데 값을 써서 기준이 바뀌어도
통과한다. 그래서 기준값 자체는 여기서 본다 — 판정해 둔 485쌍의 실제 점수로.
모델을 바꾸면 eval/same_story/score_pairs.py --write 로 점수를 다시 매기고 기준을
새로 정한다.
"""
import json
import os

from news.core import similar

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "eval", "same_story", "labeled_pairs.json")
PAIRS = json.load(open(PATH, encoding="utf-8"))["pairs"]
COLUMN = similar.EMBED_MODEL.split("/")[-1].replace("-", "_")


def _scores():
    assert COLUMN in PAIRS[0], (
        f"{similar.EMBED_MODEL} 점수가 판정 자료에 없다 — "
        "eval/same_story/score_pairs.py --write 로 다시 매기고 기준을 정하라")
    return [(p[COLUMN], p["same"]) for p in PAIRS]


def test_판정_없이_빼는_구간에_다른_기사가_없다():
    # 여기서 빠진 기사는 seen 에 들어가 다시 오지 않는다
    wrong = [s for s, same in _scores() if s >= similar.AUTO and not same]
    assert wrong == []


def test_판정에도_안_가는_같은_기사는_2퍼센트_이하다():
    same = [s for s, ok in _scores() if ok]
    missed = [s for s in same if s < similar.JUDGE]
    assert len(missed) <= 0.02 * len(same)


def test_판정_없이_빼는_구간이_같은_기사의_절반은_잡는다():
    # 기준을 너무 올려 사실상 Groq 판정에만 기대게 되는 것을 막는다
    same = [s for s, ok in _scores() if ok]
    assert sum(s >= similar.AUTO for s in same) >= 0.5 * len(same)
