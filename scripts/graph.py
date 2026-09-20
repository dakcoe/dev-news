#!/usr/bin/env python3
"""기능과 그 기능을 이루는 파일을 잇고, 끊긴 자리를 보여준다.

기능의 정의는 `_workspace/<슬러그>/` 폴더다. 66개가 이미 쌓여 있고 완료분은
`done/` 아래에 있다. 코드 주석에는 같은 슬러그가 `(add-source-silence-alert)`
꼴로 붙어 있어서, 폴더와 코드를 슬러그로 이으면 그래프가 된다.

슬러그를 코드에서 정규식으로 발굴하는 방향은 쓸 수 없었다 — HTML 속성
(data-fd)이나 문서 안 표 조각(ag-ai-n)까지 기능으로 잡힌다. 목록은 폴더에서
가져오고, 코드에서는 그 슬러그만 찾는다.

    python scripts/graph.py          기능별 구성 파일
    python scripts/graph.py --gaps   끊긴 자리만

끊긴 자리:
  코드 없음   — 폴더는 있는데 코드 어디에도 슬러그가 없다. 지운 기능이거나,
                작업하며 슬러그를 안 남긴 것이다
  테스트 없음 — 코드에는 있는데 tests/ 에 흔적이 없다

2026-09-20 arXiv 침묵 알람을 볼 때 관련 파일 다섯 개를 하나씩 찾아 헤맸다.
그 다섯은 처음부터 같은 슬러그로 묶여 있었다.
"""
from __future__ import annotations

import collections
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKSPACE = ROOT / "_workspace"
SKIP = ("venv", "__pycache__", ".git", "node_modules", "docs/data", "docs/index.html",
        "_workspace")
# worker/ 는 자바스크립트다. 처음에 파이썬 저장소로만 보고 .js 를 빼놓아서
# 동기화 Worker 가 그래프에 안 잡혔다.
EXTS = (".py", ".js", ".mjs", ".html", ".yaml", ".yml", ".sh")


def features() -> dict[str, str]:
    """슬러그 → 상태('완료' | '진행중'). 폴더가 곧 기능 목록이다."""
    out = {d.name: "진행중" for d in WORKSPACE.glob("*") if d.is_dir() and d.name != "done"}
    out.update({d.name: "완료" for d in (WORKSPACE / "done").glob("*") if d.is_dir()})
    return out


def wiring(slugs: set[str]) -> dict[str, set[pathlib.Path]]:
    """슬러그 → 그 슬러그를 언급하는 소스 파일."""
    found: dict[str, set[pathlib.Path]] = collections.defaultdict(set)
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT).as_posix()
        # 이 파일은 예시로 슬러그를 적고 있어서 자기 자신을 구성 파일로 잡는다.
        if path.suffix not in EXTS or any(s in rel for s in SKIP) or path == pathlib.Path(__file__):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for slug in slugs:
            if slug in text:
                found[slug].add(path.relative_to(ROOT))
    return found


def _kinds(files: set[pathlib.Path]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = collections.defaultdict(list)
    for f in sorted(files):
        p = f.as_posix()
        # 테스트가 두 곳이다 — 파이썬은 tests/, Worker 는 worker/test.mjs.
        kind = ("테스트" if p.startswith("tests/") or "test" in pathlib.Path(p).stem
                else "설정" if f.suffix in (".yaml", ".yml")
                else "코드")
        out[kind].append(p)
    return out


def main() -> int:
    feats = features()
    found = wiring(set(feats))
    only_gaps = "--gaps" in sys.argv

    wired = {s: f for s, f in found.items() if f}
    if not only_gaps:
        print(f"기능 {len(feats)}개 · 코드에 연결된 것 {len(wired)}개\n")
        for slug, files in sorted(wired.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            print(f"  {slug}  [{feats[slug]}]")
            for kind, paths in _kinds(files).items():
                print(f"      {kind:4s} {', '.join(paths)}")
        print()

    no_code = sorted(s for s in feats if s not in wired)
    no_test = sorted(s for s, f in wired.items() if not _kinds(f).get("테스트"))
    for name, slugs in (("코드 없음", no_code), ("테스트 없음", no_test)):
        print(f"{name} {len(slugs)}개")
        print("  " + ", ".join(slugs) if slugs else "  (없음)")
        print()
    # 보고만 한다. 지금 대부분이 비어 있어 실패로 만들면 쓸 수 없다.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
