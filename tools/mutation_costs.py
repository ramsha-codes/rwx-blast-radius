"""Diagnostics: selector cost/size on all generated mutation patches (no ground truth needed)."""
import collections, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import selector  # noqa: E402

tests = json.loads((ROOT / "sample" / "tests.json").read_text())["tests"]
by = {t["number"]: t for t in tests}
sel = selector.Selector(tests)
idx = json.loads((ROOT / "work" / "mutations" / "index.json").read_text())
agg = collections.defaultdict(lambda: [0, 0.0, 0, collections.Counter()])
big = []
for mid, info in sorted(idx.items()):
    nums, why = sel.select((ROOT / "work" / "mutations" / f"{mid}.patch").read_text())
    if nums is None:
        nums = set(sel.all_numbers)
    ws = [w for w in selector.best_split([by[n] for n in sorted(nums)]) if w]
    cost = max((sum(selector.duration_ms(by[n]) for n in w) for w in ws), default=0) / 1000 + 2 * len(ws)
    a = agg[info["kind"]]; a[0] += 1; a[1] += cost; a[2] += len(nums); a[3][why] += 1
    big.append((cost, mid, info["kind"], info["files"][0], len(nums), why, "tpcds" if any("test_execute_tpcds" in by[n]["id"] for n in nums) else ""))
for k, (n, c, s, w) in sorted(agg.items()):
    print(f"{k:8s} n={n:3d} avg_cost={c/n:6.2f}s avg_selected={s/n:6.0f} reasons={dict(w)}")
tot = sum(v[1] for v in agg.values()); n = sum(v[0] for v in agg.values())
print(f"ALL n={n} avg_cost={tot/n:.2f}s  share_with_tpcds={sum(1 for b in big if b[6])}/{n}  central={sum(1 for b in big if b[5]=='central')}")
for b in sorted(big, reverse=True)[:8]: print(b)
