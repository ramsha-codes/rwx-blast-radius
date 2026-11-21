#!/usr/bin/env python3
"""Compare coverage-only selection (current selector) with the isprof-narrowed selection for a patch dir.
Prints per-patch counts/costs and writes <out>.json with the excluded test ids per patch.
Usage: run_predict.py --profile P --patches DIR --tests sample/tests.json --out out.json
(sample answers are NOT read here.)"""
import argparse, glob, json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import selector as S
PROFILE = None
ap = argparse.ArgumentParser()
ap.add_argument("--profile"); ap.add_argument("--patches"); ap.add_argument("--tests"); ap.add_argument("--out")
a = ap.parse_args()
tests = json.load(open(a.tests))["tests"]
byn = {t["number"]: t for t in tests}
base = S.Selector(tests, profile_path=None)          # coverage-only (profile disabled)
def cost(nums):
    if not nums: return 0
    w = S.best_split([byn[n] for n in sorted(nums)])
    return max(sum(S.duration_ms(byn[n]) for n in x) for x in w) + 2000 * len(w)
out = {}; tot_b = tot_n = 0; narrowed_cnt = 0
for p in sorted(glob.glob(os.path.join(a.patches, "*.patch"))):
    pid = os.path.basename(p)[:-6]
    text = open(p, encoding="utf-8").read()
    sel = S.Selector(tests, profile_path=Path(a.profile))
    nb, _ = base.select(text); nn, _ = sel.select(text)
    nb = set(base.all_numbers) if nb is None else nb
    nn = set(base.all_numbers) if nn is None else nn
    assert nn <= nb, pid
    ex = sorted(byn[n]["id"] for n in nb - nn)
    cb, cn = cost(nb), cost(nn)
    tot_b += cb; tot_n += cn; narrowed_cnt += (nn != nb)
    out[pid] = {"cov_selected": len(nb), "narrowed_selected": len(nn), "excluded_ids": ex,
                "cost_cov_s": cb / 1000, "cost_narrowed_s": cn / 1000, "narrowed_applied": (nn != nb)}
    print(f"{pid}: cov {len(nb):4d} tests {cb/1000:6.1f}s -> narrowed {len(nn):4d} tests {cn/1000:6.1f}s  excluded {len(ex)}")
print(f"TOTAL cov {tot_b/1000:.1f}s narrowed {tot_n/1000:.1f}s saved {(tot_b-tot_n)/1000:.1f}s; predictor applied to {narrowed_cnt}/{len(out)}")
json.dump(out, open(a.out, "w"))
