#!/usr/bin/env python3
"""Build selector_map.json.gz from the pinned sqlglot checkout + a coverage run.

Map-build time only (never run by the submission). Inputs, all derived from the
pinned sqlglot commit and its own test suite (allowed by the contest rules):
  --repo   sqlglot checkout at the pinned commit
  --cov    .coverage file written by `pytest --cov --cov-context=test`
  --raw    directory of mapplugin.py JSON dumps
  --tests  tests.json (only test ids/numbers are read; no answers)

For every line of every .py file under sqlglot/ and tests/ it stores the set of
tests that must run if that line changes (rules in MILESTONE2.md). No patch or
answer information is used anywhere.
"""
import argparse
import ast
import glob
import gzip
import io
import json
import os
import sqlite3
import tokenize

ap = argparse.ArgumentParser()
ap.add_argument("--repo", required=True)
ap.add_argument("--cov", required=True)
ap.add_argument("--raw", required=True)
ap.add_argument("--tests", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()

tests = json.load(open(a.tests, encoding="utf-8"))["tests"]
ids = [t["id"] for t in tests]
idx = {t: i for i, t in enumerate(ids)}
ALL = (1 << len(ids)) - 1

# ---- coverage: file -> line -> bitset of tests ---------------------------------------
db = sqlite3.connect(a.cov)
files = {i: p for i, p in db.execute("select id, path from file")}
ctxs = {i: c for i, c in db.execute("select id, context from context")}
repo = os.path.abspath(a.repo).replace("\\", "/")
cov = {}
unmatched = set()
for fid, cid, nb in db.execute("select file_id, context_id, numbits from line_bits"):
    p = files[fid].replace("\\", "/")
    if p.startswith(repo + "/"):
        rel = p[len(repo) + 1:]
    elif p.startswith("/work/sqlglot/"):
        rel = p[len("/work/sqlglot/"):]
    else:
        continue
    ctx = ctxs[cid].split("|")[0]
    if not ctx:
        continue                     # import time / collection: not attributable to one test
    ti = idx.get(ctx)
    if ti is None:
        unmatched.add(ctx)
        continue
    bits = int.from_bytes(nb, "little")
    d = cov.setdefault(rel, {})
    ln = 0
    while bits:
        if bits & 1:
            d[ln] = d.get(ln, 0) | (1 << ti)
        bits >>= 1
        ln += 1


def group_of(t):
    return t.rsplit("::", 1)[0] if t.count("::") >= 2 else t


# ---- plugin data: fixtures opened + modules of instantiated classes --------------------
mods = {}
fixt = {}
group = {}
for i, t in enumerate(ids):
    group[group_of(t)] = group.get(group_of(t), 0) | (1 << i)
untracked = set()
seen_tests = set()
for fn in glob.glob(os.path.join(a.raw, "*.json")):
    raw = json.load(open(fn))
    untracked |= set(raw["untracked_opens"])
    for nid, ms in raw["mods"].items():
        if nid in idx:
            seen_tests.add(nid)
            for m in ms:
                mods[m] = mods.get(m, 0) | (1 << idx[nid])
    for nid, dd in raw["opens"].items():
        if nid not in idx:
            continue
        for p in dd["call"]:
            fixt[p] = fixt.get(p, 0) | (1 << idx[nid])
        for p in dd["setup"]:           # setUpClass-style reads: whole class depends on it
            fixt[p] = fixt.get(p, 0) | group[group_of(nid)]
for p in untracked:                      # read at import/collection time: any test may depend
    fixt[p] = ALL

# ---- static analysis ---------------------------------------------------------------------
sets, set_id = [], {}


def sid(b):
    k = set_id.get(b)
    if k is None:
        k = set_id[b] = len(sets)
        sets.append(b)
    return k


def modname(rel):
    m = rel[:-3].replace("/", ".")
    return m[:-9] if m.endswith(".__init__") else m


def or_range(d, lo, hi):
    r = 0
    for line in range(max(lo, 0), hi + 1):
        r |= d.get(line, 0)
    return r


docs_tests = 0
for i, t in enumerate(ids):
    if t.startswith("tests/test_docs.py"):
        docs_tests |= 1 << i


def first(s):
    return min([s.lineno] + [x.lineno for x in getattr(s, "decorator_list", [])])


def is_doc(stmts):
    s = stmts[0]
    return (isinstance(s, ast.Expr) and isinstance(getattr(s, "value", None), ast.Constant)
            and isinstance(s.value.value, str))


def analyze(rel, src, d):
    lines = src.split("\n")
    n = len(lines)
    tree = ast.parse(src)
    kind = [None] * (n + 2)
    ustart = list(range(n + 2))
    uend = list(range(n + 2))
    owner = [None] * (n + 2)
    defs = []

    def fill(lo, hi, k, own=None):
        for line in range(lo, hi + 1):
            kind[line] = k
            ustart[line] = lo
            uend[line] = hi
            owner[line] = own

    def visit(stmts, scope, own):
        for s in stmts:
            body = getattr(s, "body", None)
            if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)):
                st, en = first(s), s.end_lineno
                bs = first(s.body[0])
                dtu = (st, en, bs)
                defs.append(dtu)
                fill(st, bs - 1, "h", dtu)
                visit(s.body, "f", dtu)
            elif isinstance(s, ast.ClassDef):
                bs = first(s.body[0])
                inner = "f" if scope == "f" else "c"
                fill(first(s), bs - 1, inner, own)
                visit(s.body, inner, own)
            elif isinstance(body, list):
                bs = first(body[0])
                fill(s.lineno, bs - 1, scope, own)
                visit(body, scope, own)
                for h in getattr(s, "handlers", []):
                    fill(h.lineno, first(h.body[0]) - 1, scope, own)
                    visit(h.body, scope, own)
                for c in getattr(s, "cases", []):
                    fill(c.pattern.lineno, first(c.body[0]) - 1, scope, own)
                    visit(c.body, scope, own)
                for attr in ("orelse", "finalbody"):
                    sub = getattr(s, attr, None)
                    if sub:
                        visit(sub, scope, own)
            else:
                fill(first(s), s.end_lineno, scope, own)

    visit(tree.body, "m", None)

    def mark_doc(stmts, own):
        if stmts and is_doc(stmts):
            s = stmts[0]
            fill(s.lineno, s.end_lineno, "d", own)

    mark_doc(tree.body, None)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            mark_doc(node.body, (first(node), node.end_lineno, first(node.body[0])))
        elif isinstance(node, ast.ClassDef):
            mark_doc(node.body, None)

    in_str = [False] * (n + 2)
    spans = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.STRING and tok.end[0] > tok.start[0]:
                spans.append((tok.start[0], tok.end[0]))
                for line in range(tok.start[0], tok.end[0] + 1):
                    in_str[line] = True
    except tokenize.TokenError:
        pass

    FILE = or_range(d, 0, n + 1)
    MODS = mods.get(modname(rel), 0)
    FM = FILE | MODS

    def body_cov(dt):
        return or_range(d, dt[0], dt[1])

    def innermost(p):
        best = None
        for dt in defs:
            if dt[2] - 1 <= p <= dt[1] and (best is None or dt[0] >= best[0]):
                best = dt
        return best

    l2s = [0] * (n + 2)
    for L in range(1, n + 1):
        k = kind[L]
        txt = lines[L - 1].strip()
        if k is None:
            if not in_str[L] and (txt == "" or txt.startswith("#")):
                l2s[L] = 0                       # comment / blank: cannot change behaviour
            else:                                # else: / finally: / try: structural line
                dt = None
                for x in defs:
                    if x[2] <= L <= x[1] and (dt is None or x[0] >= dt[0]):
                        dt = x
                l2s[L] = body_cov(dt) if dt else FM
            continue
        cu = or_range(d, ustart[L], uend[L])
        if k == "f":
            l2s[L] = cu
        elif k == "h":
            l2s[L] = cu | body_cov(owner[L])
        elif k == "d":
            l2s[L] = cu | docs_tests | (body_cov(owner[L]) if owner[L] else FM)
        else:                                    # class/module level: indirect effects
            l2s[L] = cu | FM
    ins = [0] * (n + 2)
    for p in range(0, n + 1):                    # insertion after old line p
        dt = innermost(p)
        if dt is not None:
            ins[p] = body_cov(dt) | (FM if p == dt[1] else 0)
        else:
            ins[p] = FM | or_range(d, ustart[p], uend[p]) | or_range(d, ustart[p + 1], uend[p + 1])
    return {"n": n, "l2s": [sid(b) for b in l2s[:n + 1]], "ins": [sid(b) for b in ins[:n + 1]],
            "file": sid(FM), "strspans": spans}


out_files = {}
for root in ("sqlglot", "tests"):
    for dp, _, fns in os.walk(os.path.join(a.repo, root)):
        for fn in sorted(fns):
            if fn.endswith(".py"):
                full = os.path.join(dp, fn)
                rel = os.path.relpath(full, a.repo).replace("\\", "/")
                out_files[rel] = analyze(rel, open(full, encoding="utf-8").read(), cov.get(rel, {}))

fixtures = {p: sid(b) for p, b in fixt.items()}
for dp, _, fns in os.walk(os.path.join(a.repo, "tests", "fixtures")):
    for fn in fns:
        rel = os.path.relpath(os.path.join(dp, fn), a.repo).replace("\\", "/")
        fixtures.setdefault(rel, sid(0))         # never opened by any test

covered = 0
for dd in cov.values():
    for b in dd.values():
        covered |= b

# ---- tests that use a ProcessPoolExecutor ----------------------------------------------------
# Coverage cannot see work done in spawned child processes, so these tests cannot be mapped
# by line coverage. Found statically: test methods that reach `<x>.pool` / ProcessPoolExecutor
# directly or through helper methods of the same class (e.g. check_file).
def find_pool_tests():
    def uses(node):
        for x in ast.walk(node):
            if isinstance(x, ast.Attribute) and x.attr == "pool":
                return True
            if isinstance(x, ast.Name) and x.id == "ProcessPoolExecutor":
                return True
        return False

    def calls(node):
        out = set()
        for x in ast.walk(node):
            if isinstance(x, ast.Call):
                fn = x.func
                if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name)                         and fn.value.id == "self":
                    out.add(fn.attr)
                elif isinstance(fn, ast.Name):
                    out.add(fn.id)
        return out

    found = set()
    for dp, _, fns in os.walk(os.path.join(a.repo, "tests")):
        for fn in fns:
            if not fn.endswith(".py"):
                continue
            full = os.path.join(dp, fn)
            src = open(full, encoding="utf-8").read()
            if "ProcessPoolExecutor" not in src and "pool" not in src:
                continue
            rel = os.path.relpath(full, a.repo).replace(os.sep, "/")
            tree = ast.parse(src)
            modfn = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
            pool_fns = {k for k, v in modfn.items() if uses(v)}
            for c in (n for n in tree.body if isinstance(n, ast.ClassDef)):
                meths = {n.name: n for n in c.body if isinstance(n, ast.FunctionDef)}
                dep = {k for k, v in meths.items() if k != "setUpClass" and uses(v)}
                changed = True
                while changed:
                    changed = False
                    for k, v in meths.items():
                        if k not in dep and calls(v) & (dep | pool_fns):
                            dep.add(k)
                            changed = True
                for k in dep:
                    tid = rel + "::" + c.name + "::" + k
                    if tid in idx:
                        found.add(idx[tid])
    return sorted(found)


pool_tests = find_pool_tests()

result = {
    "version": 1,
    "pinned_commit": "eb11aec4be8cb2122afe713a4816662c3f0fb2fa",
    "tests": ids,
    "sets": [format(b, "x") for b in sets],
    "files": out_files,
    "fixtures": fixtures,
    "pool_tests": pool_tests,
    "unmapped_tests": [i for i in range(len(ids)) if not (covered >> i) & 1],
}
with gzip.open(a.out, "wt", encoding="utf-8", compresslevel=9) as f:
    json.dump(result, f, separators=(",", ":"))
print("tests", len(ids), "sets", len(sets), "files", len(out_files), "fixtures", len(fixtures),
      "unmapped", len(result["unmapped_tests"]), "unmatched ctx", len(unmatched),
      "size", os.path.getsize(a.out))
for u in sorted(unmatched)[:10]:
    print("  unmatched:", u)
print("pool-dependent tests:", len(pool_tests),
      "recorded seconds:", round(sum(tests[i]["seconds"] for i in pool_tests), 3))
