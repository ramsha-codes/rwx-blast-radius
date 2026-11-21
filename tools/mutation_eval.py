#!/usr/bin/env python3
"""Validation only: compare the selector's choice for each mutation patch with the tests that
really failed (work/mutres/<id>.json from tools/run_mutations.sh).

Usage: python tools/mutation_eval.py [--map selector_map.json.gz] [--no-pool-rule] [-v]
Prints hit/miss statistics, selected-test counts, scheduled seconds, and each miss with the
unselected failing tests. Nothing here feeds back into the selector as a lookup.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import selector  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--map", default=str(ROOT / "selector_map.json.gz"))
ap.add_argument("--no-pool-rule", action="store_true")
ap.add_argument("--muts", default=str(ROOT / "work" / "mutations"))
ap.add_argument("--res", default=str(ROOT / "work" / "mutres"))
ap.add_argument("-v", action="store_true")
a = ap.parse_args()

tests = json.loads((ROOT / "sample" / "tests.json").read_text())["tests"]
num_by_id = {t["id"]: t["number"] for t in tests}
by_number = {t["number"]: t for t in tests}
sel = selector.Selector(tests, Path(a.map))
if a.no_pool_rule:
    sel.pool_bits = 0
index = json.loads((Path(a.muts) / "index.json").read_text())

stats = {}
total_cost = 0
n_eval = n_miss = n_fail_commits = 0
for mid, info in sorted(index.items()):
    rp = Path(a.res) / f"{mid}.json"
    if not rp.exists():
        continue
    r = json.loads(rp.read_text())
    failing = {num_by_id[x] for x in r["failed"] if x in num_by_id}
    for f in r["collect_errors"]:
        failing |= {t["number"] for t in tests if t["file"] == f.split("::")[0]}
    unknown = [x for x in r["failed"] if x not in num_by_id]
    nums, why = sel.select((Path(a.muts) / f"{mid}.patch").read_text())
    if nums is None:
        nums = set(sel.all_numbers)
    ws = selector.best_split([by_number[n] for n in sorted(nums)])
    cost = (max((sum(selector.duration_ms(by_number[n]) for n in w) for w in ws), default=0)
            + 2000 * len([w for w in ws if w])) / 1000
    missed = sorted(failing - nums)
    k = info["kind"]
    s = stats.setdefault(k, {"n": 0, "miss": 0, "fail_commits": 0, "sel": 0, "cost": 0.0})
    s["n"] += 1; s["sel"] += len(nums); s["cost"] += cost
    s["fail_commits"] += bool(failing); s["miss"] += bool(missed)
    n_eval += 1; n_miss += bool(missed); n_fail_commits += bool(failing); total_cost += cost
    if missed or a.v:
        print(f"{mid} {k:8s} {info['files'][0]:45s} failing={len(failing):4d} selected={len(nums):4d} "
              f"cost={cost:6.1f} missed={[by_number[n]['id'].split('::', 1)[1] for n in missed][:4]}"
              f"{' UNKNOWN_IDS=' + str(unknown[:2]) if unknown else ''}")
print(f"\nevaluated={n_eval} commits_with_real_failures={n_fail_commits} "
      f"MISSED_COMMITS={n_miss} avg_cost={total_cost / max(n_eval, 1):.2f}s "
      f"(a miss would add 300 s each)")
for k, s in sorted(stats.items()):
    print(f"  {k:8s} n={s['n']:3d} real_failures={s['fail_commits']:3d} missed={s['miss']:2d} "
          f"avg_selected={s['sel'] / s['n']:6.1f} avg_cost={s['cost'] / s['n']:6.1f}s")
