"""Build-time: compact the M18 per-query profile (pristine pinned commit) into tpcds_micro_profile.json.gz.
narrow: file -> {line: [query ids]} for lines reached by 1..K queries; wide: lines reached by >K queries;
G: shared / import / setup / first-touch lines. Any changed line in G or wide => no micro-check."""
import gzip, hashlib, json, sys
from collections import defaultdict
K = 20
P = json.load(open(sys.argv[1])); tests = json.load(open(sys.argv[2]))["tests"]
per = defaultdict(list)
for q, ls in P["per"].items():
    for f, l in ls: per[(f, l)].append(int(q))
narrow = defaultdict(dict); wide = defaultdict(list); G = defaultdict(list)
for (f, l), qs in per.items():
    if len(qs) <= K: narrow[f][str(l)] = sorted(qs)
    else: wide[f].append(l)
for f, l in P["G"]: G[f].append(l)
out = {"version": 1, "pinned": "eb11aec4be8cb2122afe713a4816662c3f0fb2fa", "K": K,
       "test": "tests/test_executor.py::TestExecutor::test_execute_tpcds",
       "exec": P["exec"], "fp": {q: [v["duck"], v["res"]] for q, v in P["fp"].items()}, "cpu": P["cpu"],
       "narrow": narrow, "wide": {f: sorted(v) for f, v in wide.items()}, "G": {f: sorted(v) for f, v in G.items()}}
with gzip.open(sys.argv[3], "wt", encoding="utf-8") as fh: json.dump(out, fh, separators=(",", ":"))
print("narrow lines", sum(len(v) for v in narrow.values()), "wide", sum(len(v) for v in wide.values()), "G", sum(len(v) for v in G.values()))
