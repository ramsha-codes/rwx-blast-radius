import json, glob, os, sys
from pathlib import Path
sys.path.insert(0, ".")
import selector
tests = json.load(open("sample/tests.json"))["tests"]; byn = {t["number"]: t for t in tests}; num = {t["id"]: t["number"] for t in tests}
M11 = selector.Selector(tests, clsprof_path=None); M15 = selector.Selector(tests)
def cost(nums):
    if not nums: return 0.0
    ws = selector.best_split([byn[n] for n in sorted(nums)])
    return (max(sum(selector.duration_ms(byn[n]) for n in w) for w in ws) + 2000 * len(ws)) / 1000
def failing(fr):
    f = {num[x] for x in fr["failed"] if x in num}
    for c in fr.get("collect_errors", []): f |= {t["number"] for t in tests if t["file"] == c.split("::")[0]}
    return f
TP = num["tests/test_executor.py::TestExecutor::test_execute_tpcds"]
ans = json.load(open("sample/answers.json"))["commits"]
corp = {"sample": [(p, set(ans[Path(p).stem]["failing"]), None) for p in sorted(glob.glob("sample/commits/*.patch"))]}
corp["m11_repro"] = [(f"work/m11cand/repro/{Path(p).stem}.patch", failing(json.load(open(f"work/m11/mutres/{Path(p).stem}.json"))) if os.path.exists(f"work/m11/mutres/{Path(p).stem}.json") else failing(json.load(open(f"work/m11/gt/{Path(p).stem}/fail.json"))) & {TP}, None) for p in sorted(glob.glob("work/m11cand/repro/*.patch"))]
corp["m11_newcred"] = [(f"work/m11ov/newcred/{Path(p).stem}.patch", failing(json.load(open(p))), None) for p in sorted(glob.glob("work/m11ov/newcred_res/*.json"))]
corp["m3_general"] = [(p, failing(json.load(open(f"work/mutres/{Path(p).stem}.json"))) if os.path.exists(f"work/mutres/{Path(p).stem}.json") else None, None) for p in sorted(glob.glob("work/mutations/*.patch"))]
for name, hd, vd, rd in (("m9_heldout", "work/clsprof_heldout", "work/clsprof_val", "work/clsprof_valres"), ("m9_heldout2", "work/clsprof_heldout2", "work/clsprof_val2", "work/clsprof_valres2"),
                         ("isprof_heldout", "work/isprof/heldout", "work/isprof/val", "work/isprof/valres"), ("isprof_heldout2", "work/isprof/heldout2", "work/isprof/val2", "work/isprof/valres2")):
    corp[name] = []
    for p in sorted(glob.glob(hd + "/*.patch")):
        pid = Path(p).stem; ids = f"{vd}/{pid}.ids"; r = f"{rd}/{pid}.json"
        scope = {num[x.strip()] for x in open(ids) if x.strip() in num} if os.path.exists(ids) else None
        corp[name].append((p, failing(json.load(open(r))) if os.path.exists(r) else None, scope))
corp["m10_fresh"] = [(p, None, None) for p in sorted(glob.glob("work/m10val/fresh/*.patch"))]
need = {}
tot = {"a": 0, "b": 0}
print("%-16s %4s %8s %9s %9s %7s %s" % ("corpus", "n", "narrowed", "M11 cost", "M15 cost", "misses", "excluded tests not covered by an earlier validation run"))
for name, rows in corp.items():
    a = b = 0; nar = 0; miss = 0; unval = 0
    for p, fail, scope in rows:
        t = open(p, encoding="utf-8", errors="replace").read()
        s1, _ = M11.select(t); s2, _ = M15.select(t); s1 = set(byn) if s1 is None else s1; s2 = set(byn) if s2 is None else s2
        assert s2 <= s1
        a += cost(s1); b += cost(s2)
        if fail is not None and fail - s2: miss += 1
        if s2 != s1:
            nar += 1; ex = s1 - s2
            covered = (scope or set()) if fail is None or scope is not None else set(byn)   # full labels cover everything
            if fail is not None and scope is None: covered = set(byn)
            rest = ex - covered
            if rest: unval += 1; need[p] = sorted(byn[n]["id"] for n in rest)
    tot["a"] += a; tot["b"] += b
    print("%-16s %4d %8d %9.1f %9.1f %7d %d patches" % (name, len(rows), nar, a, b, miss, unval))
print("TOTAL M11 %.1f -> M15 %.1f (%.1f s, %.1f%%)" % (tot["a"], tot["b"], tot["a"] - tot["b"], 100 * (tot["a"] - tot["b"]) / tot["a"]))
json.dump(need, open("work/m15/need_validation.json", "w"), indent=0)
print("patches needing excluded-test execution:", len(need), "tests:", sum(len(v) for v in need.values()))
