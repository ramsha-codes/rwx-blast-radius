"""Candidate-map checks vs the M8 map (git 10eb5b5). usage: python tools/m11cand/verify_map.py <m8_map> <cand_map> <tests.json> [gap370.json]"""
import gzip, hashlib, json, sys
a = json.load(gzip.open(sys.argv[1])); b = json.load(gzip.open(sys.argv[2])); tests = json.load(open(sys.argv[3]))["tests"]
ok = True
def check(cond, msg):
    global ok
    print(("PASS " if cond else "FAIL ") + msg); ok &= bool(cond)
check(b["version"] == a["version"] and b["pinned_commit"] == a["pinned_commit"], "version / pinned commit unchanged")
check(b["tests"] == a["tests"], "test id list and order identical to M8 (%d)" % len(b["tests"]))
check(not ({t["id"] for t in tests} - set(b["tests"])), "every tests.json id is mapped")
check(set(b["files"]) == set(a["files"]), "same %d mapped files" % len(b["files"]))
check(b["fixtures"].keys() == a["fixtures"].keys(), "same fixture keys")
for k in ("pool_tests", "proc_tests", "unmapped_tests"):
    check(b[k] == a[k], k + " unchanged")
p = json.load(gzip.open("isprof_profile.json.gz", "rt"))
check(p["tests_sha"] == hashlib.sha1(json.dumps(b["tests"]).encode()).hexdigest(), "isprof profile tests_sha matches candidate map")
sa = [int(h, 16) if h else 0 for h in a["sets"]]; sb = [int(h, 16) if h else 0 for h in b["sets"]]
shrunk = grown = 0
for f, ea in a["files"].items():
    eb = b["files"][f]
    if eb["n"] != ea["n"] or eb["strspans"] != ea["strspans"]: check(False, "geometry changed " + f)
    for key in ("l2s", "ins"):
        for x, y in zip(ea[key], eb[key]):
            X, Y = sa[x], sb[y]
            shrunk += bool(X & ~Y); grown += bool(Y & ~X)
    if sa[ea["file"]] != sb[eb["file"]]: check(False, "file-level set changed " + f)
    fa = {p: sa[i] for p, i in a["fixtures"].items()}; fb = {p: sb[i] for p, i in b["fixtures"].items()}
check(shrunk == 0, "no line/insertion set lost any test (superset of M8); grown entries: %d" % grown)
check(all(fa[k] == fb[k] for k in fa), "fixture sets identical")
if len(sys.argv) > 4:
    B = b["tests"].index("tests/test_executor.py::TestExecutor::test_execute_tpcds")
    rows = json.load(open(sys.argv[4]))
    miss = [(r["file"], r["line"]) for r in rows if not sb[b["files"]["sqlglot/" + r["file"]]["l2s"][r["line"]]] >> B & 1]
    check(not miss, "all %d audit gap statements now select tpcds (missing: %s)" % (len(rows), miss[:5]))
print("RESULT:", "ALL PASS" if ok else "FAILED"); sys.exit(0 if ok else 1)
