"""Diagnostics: per-commit cost breakdown of the current selector on the sample."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import selector  # noqa: E402

sample = ROOT / "sample"
tests = json.loads((sample / "tests.json").read_text())["tests"]
by = {t["number"]: t for t in tests}
ans = json.loads((sample / "answers.json").read_text())["commits"]
sel = selector.Selector(tests)
rows = []
for p in sorted((sample / "commits").glob("*.patch")):
    text = p.read_text(encoding="utf-8")
    nums, why = sel.select(text)
    if nums is None:
        nums = set(sel.all_numbers)
    ws = [w for w in selector.best_split([by[n] for n in sorted(nums)]) if w]
    mk = max((sum(selector.duration_ms(by[n]) for n in w) for w in ws), default=0) / 1000
    top = sorted(nums, key=lambda n: -by[n]["seconds"])[:3]
    files = [f["old"] for f in (selector.parse_patch(text) or [])]
    rows.append((p.stem, ans[p.stem]["kind"], why, len(nums), len(ws), mk, mk + 2 * len(ws),
                 [(by[n]["id"].split("::", 1)[1], by[n]["seconds"]) for n in top], files))
tot = sum(r[6] for r in rows)
print(f"TOTAL {tot:.1f}s  (makespan {sum(r[5] for r in rows):.1f} + worker overhead {sum(2*r[4] for r in rows):.1f})")
for r in sorted(rows, key=lambda r: -r[6]):
    print(f"{r[0]} {r[1]:7s} {r[2]:8s} n={r[3]:5d} w={r[4]} makespan={r[5]:6.2f} cost={r[6]:6.2f} files={[f.split('/')[-1] for f in r[8]]} top={[(a.split('::')[-1], s) for a, s in r[7]]}")
