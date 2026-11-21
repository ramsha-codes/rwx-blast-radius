#!/usr/bin/env python3
"""Generate seeded held-out single-site `is`->`==` / `is not`->`!=` mutation patches from sites.json (all
sites eligible for the predictor: one `is` on a single-line comparison). Excludes the two sample-edit lines
(sqlglot/dialects/dialect.py case_sensitive, sqlglot/executor/context.py) so the set is independent of the sample.
Usage: heldout.py --repo work/sqlglot --sites work/isprof/sites.json --out work/isprof/heldout --n 40 --seed 20261121
"""
import argparse, difflib, json, os, random, re
ap = argparse.ArgumentParser()
ap.add_argument("--repo"); ap.add_argument("--sites"); ap.add_argument("--out")
ap.add_argument("--exclude-dir", default=None); ap.add_argument("--n", type=int, default=40); ap.add_argument("--seed", type=int, default=20261121)
a = ap.parse_args()
rng = random.Random(a.seed)
sites = json.load(open(a.sites))["sites"]
EXCL = {("sqlglot/dialects/dialect.py", 1280), ("sqlglot/executor/context.py", 53)}
cache = {}
if a.exclude_dir:
    for v in json.load(open(os.path.join(a.exclude_dir, "index.json"))).values():
        EXCL.add((v["file"], v["line"]))
def lines(f):
    if f not in cache:
        cache[f] = open(os.path.join(a.repo, f), encoding="utf-8", newline="").read().split("\n")
    return cache[f]
elig = []
for s in sites:
    if s["line"] != s["end_line"] or s["ord"] != 0 or (s["file"], s["line"]) in EXCL:
        continue
    L = lines(s["file"])[s["line"] - 1]
    if len(re.findall(r"\bis\b", L)) != 1:
        continue
    pat = r"\bis not\b" if s["op"] == "is not" else r"\bis\b(?! not)"
    if len(re.findall(pat, L)) != 1 or "#" in L or '"' in L.split("is")[0] and False:
        continue
    elig.append(s)
rng.shuffle(elig)
os.makedirs(a.out, exist_ok=True)
index = {}
for k, s in enumerate(elig[:a.n]):
    f, ln = s["file"], s["line"]
    old = lines(f)
    L = old[ln - 1]
    new_line = re.sub(r"\bis not\b", "!=", L, count=1) if s["op"] == "is not" else re.sub(r"\bis\b", "==", L, count=1)
    new = list(old); new[ln - 1] = new_line
    body = list(difflib.unified_diff(old, new, f"a/{f}", f"b/{f}", n=3, lineterm=""))
    pid = f"h{k:03d}"
    open(os.path.join(a.out, pid + ".patch"), "w", encoding="utf-8", newline="\n").write(f"diff --git a/{f} b/{f}\n" + "\n".join(body) + "\n")
    index[pid] = {"file": f, "line": ln, "op": s["op"], "site": s["id"]}
json.dump(index, open(os.path.join(a.out, "index.json"), "w"), indent=1)
print(f"eligible pool {len(elig)}; wrote {min(a.n, len(elig))} patches")
