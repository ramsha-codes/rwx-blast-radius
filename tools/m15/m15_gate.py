import gzip, json, glob, os, sys
from pathlib import Path
sys.path.insert(0, "work/m12"); sys.path.insert(0, ".")
import selector
from predict import ClsProfSelector
tests = json.load(open("sample/tests.json"))["tests"]; byn = {t["number"]: t for t in tests}; num = {t["id"]: t["number"] for t in tests}
A = json.load(gzip.open("work/m11ov/m8_map.json.gz")); B = json.load(gzip.open("selector_map.json.gz"))
sa = [int(h, 16) if h else 0 for h in A["sets"]]; sb = [int(h, 16) if h else 0 for h in B["sets"]]
P = json.load(gzip.open("work/m15/clsprof_profile_m11.json.gz", "rt"))
diff = 0; lines = 0
for key in P["sites"]:
    path, s, e = key.rsplit(":", 2)
    for L in range(int(s), int(e) + 1):
        lines += 1
        for k in ("l2s", "ins"):
            if sa[A["files"][path][k][L]] != sb[B["files"][path][k][L]]: diff += 1
for key in P["sites"]:
    path, s, e = key.rsplit(":", 2); L = int(s) - 1
    if sa[A["files"][path]["ins"][L]] != sb[B["files"][path]["ins"][L]]: diff += 1
print("(a) M9 site lines:", lines, " entries where M11 line/insertion sets differ from M8:", diff)
base = selector.Selector(tests); m9 = ClsProfSelector(tests, profile_path="work/m15/clsprof_profile_m11.json.gz")
def failing(fr):
    f = {num[x] for x in fr["failed"] if x in num}
    for c in fr.get("collect_errors", []): f |= {t["number"] for t in tests if t["file"] == c.split("::")[0]}
    return f
TP = num["tests/test_executor.py::TestExecutor::test_execute_tpcds"]
lab = []
ans = json.load(open("sample/answers.json"))["commits"]
lab += [("sample", p, set(ans[Path(p).stem]["failing"])) for p in sorted(glob.glob("sample/commits/*.patch"))]
for m in ("gA00", "gC01"): lab.append(("repro-full", f"work/m11cand/repro/{m}.patch", failing(json.load(open(f"work/m11/mutres/{m}.json")))))
for d in sorted(glob.glob("work/m11/gt/*")):
    lab.append(("repro-tpcds", f"work/m11cand/repro/{Path(d).name}.patch", failing(json.load(open(d + "/fail.json"))) & {TP}))
for p in sorted(glob.glob("work/m11ov/newcred_res/*.json")): lab.append(("newcred-full", f"work/m11ov/newcred/{Path(p).stem}.patch", failing(json.load(open(p)))))
for m in ("m000", "m001", "m002", "m003"): lab.append(("general-full", f"work/mutations/{m}.patch", failing(json.load(open(f"work/mutres/{m}.json")))))
for d in sorted(glob.glob("work/m10val/gt/*")):
    pid = Path(d).name
    pp = (glob.glob(f"work/mutations/{pid}.patch") + glob.glob(f"work/isprof/heldout/{pid}.patch") + glob.glob(f"work/m10val/fresh/{pid}.patch")
          + glob.glob(f"sample/commits/{pid.replace('ctrl_', '')}.patch"))
    if pp: lab.append(("m10-tpcds", pp[0], failing(json.load(open(d + "/fail.json"))) & {TP}))
for vd, rd, hd in (("work/clsprof_val", "work/clsprof_valres", "work/clsprof_heldout"), ("work/clsprof_val2", "work/clsprof_valres2", "work/clsprof_heldout2"),
                   ("work/isprof/val", "work/isprof/valres", "work/isprof/heldout"), ("work/isprof/val2", "work/isprof/valres2", "work/isprof/heldout2")):
    for r in sorted(glob.glob(rd + "/*.json")):
        pid = Path(r).stem
        if os.path.exists(f"{hd}/{pid}.patch"): lab.append(("partial:" + Path(rd).name, f"{hd}/{pid}.patch", failing(json.load(open(r)))))
viol = []; narrowed = 0; recovered_kept = 0; rec_total = 0
from collections import Counter
cnt = Counter()
for src, p, fail in lab:
    t = open(p, encoding="utf-8", errors="replace").read()
    s1, _ = base.select(t); s2, _ = m9.select(t)
    s1 = set(byn) if s1 is None else s1; s2 = set(byn) if s2 is None else s2
    assert s2 <= s1
    cnt[src] += 1
    if s2 != s1: narrowed += 1
    if fail - s2: viol.append((src, Path(p).stem, len(fail - s2), len(fail - s1)))
    if src in ("repro-full", "newcred-full") or src == "repro-tpcds":
        rec_total += len(fail); recovered_kept += len(fail & s2)
print("(b) labeled patches checked:", dict(cnt), " narrowed by M9:", narrowed)
print("    labeled failing tests NOT selected by M11+M9:", viol if viol else "none")
print("    M11-recovered failing tests (repro full+tpcds, newcred full) still selected: %d / %d" % (recovered_kept, rec_total))
