#!/usr/bin/env python3
"""Merge isprof dumps (one or more independent runs) into a compact certification profile.
A (test, site) pair is CERTIFIED (flip `is`<->`==` provably cannot change that test's behaviour in the
profiled run) iff in EVERY run: the pair was observed with safe operand types, never infected, never
unsupported; the site was never infected/unsupported in the unattributed phase (import/collection/fixtures);
and both runs saw the same observation state for the pair (nondeterminism -> not certified).
Usage: merge.py --sites sites.json --map selector_map.json.gz --out isprof_profile.json.gz RUNDIR [RUNDIR...]
"""
import argparse, glob, gzip, hashlib, json, os

ap = argparse.ArgumentParser()
ap.add_argument("--sites"); ap.add_argument("--map"); ap.add_argument("--out")
ap.add_argument("runs", nargs="+")
a = ap.parse_args()
sites = json.load(open(a.sites))["sites"]
m = json.load(gzip.open(a.map, "rt"))
bit = {t: i for i, t in enumerate(m["tests"])}


def load(rundir):
    per = {}           # test -> [S, I, U]
    for p in glob.glob(os.path.join(rundir, "*.json")):
        for t, d in json.load(open(p)).items():
            e = per.setdefault(t, [set(), set(), set()])
            e[0].update(d["s"]); e[1].update(d["i"]); e[2].update(d["u"])
    return per

runs = [load(r) for r in a.runs]
nsites = len(sites)
stats = {"sites": nsites, "runs": len(runs)}
glob_bad = set()
for per in runs:
    g = per.get("", [set(), set(), set()])
    glob_bad |= g[1] | g[2]
executed = set()
cert = {}     # site -> set(bit)
unattrib_executed = set()
for per in runs:
    for t, (S, I, U) in per.items():
        executed |= S | I | U
        if t == "":
            unattrib_executed |= S | I | U
tests_seen = set()
for t in set().union(*[set(p) for p in runs]):
    if t == "" or t not in bit:
        continue
    tests_seen.add(t)
    states = []
    for per in runs:
        S, I, U = per.get(t, [set(), set(), set()])
        states.append((frozenset(S), frozenset(I), frozenset(U)))
    # nondeterminism: observation sets differ between runs
    base = states[0]
    for site in set().union(*[s[0] | s[1] | s[2] for s in states]):
        obs = [(site in s[0], site in s[1], site in s[2]) for s in states]
        if len(set(obs)) != 1:
            continue
        s_, i_, u_ = obs[0]
        if s_ and not i_ and not u_ and site not in glob_bad:
            cert.setdefault(site, set()).add(bit[t])
site_bits = {}
for site, bs in cert.items():
    v = 0
    for b in bs: v |= 1 << b
    site_bits[site] = v
sets, idx, rows = {}, [], {}
for site, v in sorted(site_bits.items()):
    h = format(v, "x")
    if h not in sets: sets[h] = len(sets)
    s = sites[site]
    rows[f'{s["file"]}:{s["line"]}:{s["end_line"]}:{s["ord"]}:{s["op"]}'] = sets[h]
out = {"version": 1, "tests_sha": hashlib.sha1(json.dumps(m["tests"]).encode()).hexdigest(), "sets": list(sets), "sites": rows, "n_sites": nsites,
       "n_certified_sites": len(rows), "n_executed_sites": len(executed),
       "n_unattributed_sites": len(unattrib_executed), "n_glob_bad": len(glob_bad)}
with gzip.open(a.out, "wt") as f: json.dump(out, f, separators=(",", ":"))
print(json.dumps({k: v for k, v in out.items() if k not in ("sets", "sites")}),
      "profile bytes", os.path.getsize(a.out), "pairs", sum(bin(v).count('1') for v in site_bits.values()))
