"""같은 사건 거르기 — 임베딩과 판정 모델은 가짜로 바꿔 흐름만 본다."""
from news.core import similar


def _art(url, title):
    return {"url": url, "title": title, "summary": ""}


def _embed_by(table):
    """제목 → 단위 벡터. 두 벡터의 내적이 원하는 유사도가 되게 만든다."""
    def embed(texts):
        return [table[t.split(".")[0]] for t in texts]
    return embed


def _vec(sim):
    return [sim, (1 - sim ** 2) ** 0.5]


BASE = [1.0, 0.0]


class _Judge:
    def __init__(self, answer):
        self.answer, self.asked = answer, []

    def same(self, a, b):
        self.asked.append((a["url"], b["url"]))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def test_유사도가_아주_높으면_판정_없이_뺀다():
    old, new = _art("o", "old"), _art("n", "new")
    j = _Judge(False)
    kept, dropped = similar.drop_same_story([new], [old], judge=j,
                                            embed=_embed_by({"old": BASE, "new": _vec(0.9)}))
    assert kept == [] and dropped[0]["same_as"] == "o" and j.asked == []


def test_경계_구간은_판정에_맡긴다():
    old, new = _art("o", "old"), _art("n", "new")
    emb = _embed_by({"old": BASE, "new": _vec(0.7)})
    kept, _ = similar.drop_same_story([new], [old], judge=_Judge(False), embed=emb)
    assert kept == [new]
    kept, dropped = similar.drop_same_story([new], [old], judge=_Judge(True), embed=emb)
    assert kept == [] and dropped[0]["same_as"] == "o"


def test_유사도가_낮으면_묻지도_않는다():
    j = _Judge(True)
    kept, _ = similar.drop_same_story([_art("n", "new")], [_art("o", "old")], judge=j,
                                      embed=_embed_by({"old": BASE, "new": _vec(0.5)}))
    assert len(kept) == 1 and j.asked == []


def test_같은_회차_안에서는_앞선_기사를_남긴다():
    first, second = _art("a", "first"), _art("b", "second")
    kept, dropped = similar.drop_same_story(
        [first, second], [], judge=_Judge(False),
        embed=_embed_by({"first": BASE, "second": _vec(0.95)}))
    assert kept == [first] and dropped[0]["url"] == "b"


def test_판정_모델이_안_떠도_유사도로는_거른다():
    old = _art("o", "old")
    near, auto = _art("n1", "near"), _art("n2", "auto")
    kept, dropped = similar.drop_same_story(
        [near, auto], [old], judge=_Judge(RuntimeError("mlx 없음")),
        embed=_embed_by({"old": BASE, "near": _vec(0.7), "auto": _vec(0.9)}))
    assert kept == [near] and [d["url"] for d in dropped] == ["n2"]


def test_임베딩이_실패하면_아무것도_빼지_않는다():
    def boom(texts):
        raise ImportError("sentence_transformers 없음")
    new = [_art("n", "new")]
    assert similar.drop_same_story(new, [_art("o", "old")], judge=_Judge(True), embed=boom) == (new, [])


def test_판정은_기사당_몇_번까지만_묻는다():
    olds = [_art(f"o{i}", f"old{i}") for i in range(6)]
    table = {f"old{i}": BASE for i in range(6)} | {"new": _vec(0.7)}
    j = _Judge(False)
    similar.drop_same_story([_art("n", "new")], olds, judge=j, embed=_embed_by(table))
    assert len(j.asked) == similar.MAX_JUDGE_PER_ARTICLE
