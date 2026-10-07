"""판정해 둔 쌍(labeled_pairs.json)을 지금 similar.py 설정으로 다시 채점한다.

임베딩 모델이나 입력·프롬프트를 바꿀 때 돌린다. 새 점수를 파일에 적고, 오탐 없이
판정 없이 뺄 수 있는 가장 낮은 값(AUTO 후보)과 같은 기사를 몇 쌍 놓치는지 보여 준다.
기준값을 정한 뒤 tests/test_same_story_thresholds.py 가 그 값을 지킨다.

    venv/bin/python eval/same_story/score_pairs.py            # 점수만 보기
    venv/bin/python eval/same_story/score_pairs.py --write    # 파일의 점수 열을 갱신
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "labeled_pairs.json")

from news.core import similar  # noqa: E402

data = json.load(open(PATH, encoding="utf-8"))
pairs = data["pairs"]
texts = [p["a"] for p in pairs] + [p["b"] for p in pairs]
vecs = similar._embed(texts)
n = len(pairs)
scores = [round(similar._dot(vecs[i], vecs[n + i]), 4) for i in range(n)]

order = sorted(range(n), key=lambda i: -scores[i])
first_wrong = next(k for k, i in enumerate(order) if not pairs[i]["same"])
auto = scores[order[first_wrong - 1]] if first_wrong else None
same_total = sum(p["same"] for p in pairs)
print(f"판정 {n}쌍 · 같은 기사 {same_total}쌍")
print(f"오탐 없이 위에서 {first_wrong}쌍 — AUTO 후보 {auto}")
for judge in (0.85, 0.88, 0.9):
    missed = sum(1 for i in range(n) if pairs[i]["same"] and scores[i] < judge)
    print(f"JUDGE {judge}: 그 아래로 내려간 같은 기사 {missed}쌍")

if "--write" in sys.argv:
    key = similar.EMBED_MODEL.split("/")[-1].replace("-", "_")
    for p, s in zip(pairs, scores):
        p[key] = s
    json.dump(data, open(PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(f"{PATH} 의 {key} 열을 갱신했다")
