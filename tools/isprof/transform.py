#!/usr/bin/env python3
"""Milestone 8 prototype (isolated, build-time only): rewrite simple `a is b` / `a is not b`
comparisons inside function bodies as `_isp(SITE, (a), (b))`, preserving evaluation order, evaluating each
operand exactly once, and keeping the line count identical. `_isp` is injected into builtins by
tools/isprof/rt/sitecustomize.py. Module-level and class-level code (import-time execution) is NOT instrumented.

Usage: python tools/isprof/transform.py <pristine sqlglot pkg dir> <out pkg dir> <sites.json>
Nothing here is imported by selector.py.
"""
import ast
import json
import os
import shutil
import sys

src_dir, out_dir, sites_path = sys.argv[1:4]
FUNC = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


class Finder(ast.NodeVisitor):
    def __init__(self):
        self.found = []        # Compare nodes (instrumentable)
        self.skipped = {"import-time": 0, "multiline-gap": 0, "chained": 0}
        self.depth = 0

    def visit_FunctionDef(self, n):
        self.depth += 1
        self.generic_visit(n)
        self.depth -= 1
    visit_AsyncFunctionDef = visit_FunctionDef
    visit_Lambda = visit_FunctionDef

    def visit_Compare(self, n):
        if any(isinstance(o, (ast.Is, ast.IsNot)) for o in n.ops):
            if len(n.ops) != 1:
                self.skipped["chained"] += 1
            elif self.depth == 0:
                self.skipped["import-time"] += 1
            else:
                self.found.append(n)
        self.generic_visit(n)


def offsets(data: bytes):
    starts, pos = [0], 0
    for line in data.split(b"\n"):
        pos += len(line) + 1
        starts.append(pos)
    return starts


def convert(path_rel, data: bytes, site_rows, counters):
    tree = ast.parse(data.decode("utf-8"))
    f = Finder()
    f.visit(tree)
    for k, v in f.skipped.items():
        counters[k] += v
    ls = offsets(data)
    def off(lineno, col):
        return ls[lineno - 1] + col
    targets = []
    for n in f.found:
        s, e = off(n.lineno, n.col_offset), off(n.end_lineno, n.end_col_offset)
        l_s, l_e = off(n.left.lineno, n.left.col_offset), off(n.left.end_lineno, n.left.end_col_offset)
        r = n.comparators[0]
        r_s, r_e = off(r.lineno, r.col_offset), off(r.end_lineno, r.end_col_offset)
        if b"\n" in data[l_e:r_s]:          # operator on another line: skip (keeps line numbers exact)
            counters["multiline-gap"] += 1
            continue
        # operands wrapped in parens in the source: widen to include them so we do not unbalance
        targets.append({"s": s, "e": e, "ls": l_s, "le": l_e, "rs": r_s, "re": r_e, "n": n})
    # ordinal among sites starting on the same line, left-to-right
    by_line = {}
    for t in targets:
        by_line.setdefault(t["n"].lineno, []).append(t)
    for line, ts in by_line.items():
        ts.sort(key=lambda t: t["s"])
        for i, t in enumerate(ts):
            t["ord"] = i
    for t in targets:
        n = t["n"]
        t["id"] = len(site_rows)
        site_rows.append({"id": t["id"], "file": path_rel, "line": n.lineno, "end_line": n.end_lineno,
                          "ord": t["ord"], "op": "is not" if isinstance(n.ops[0], ast.IsNot) else "is"})
    targets.sort(key=lambda t: (t["s"], -t["e"]))

    def render(start, end, inner):
        """original bytes[start:end] with the targets in `inner` (sorted, contained) replaced"""
        out, pos, i = [], start, 0
        while i < len(inner):
            t = inner[i]
            if t["s"] < pos:       # nested inside an already rendered target
                i += 1
                continue
            out.append(data[pos:t["s"]])
            kids = [u for u in inner if u is not t and u["s"] >= t["s"] and u["e"] <= t["e"]]
            left = render(t["ls"], t["le"], [u for u in kids if u["e"] <= t["le"]])
            right = render(t["rs"], t["re"], [u for u in kids if u["s"] >= t["rs"]])
            fn = b"_ispn" if isinstance(t["n"].ops[0], ast.IsNot) else b"_isp"
            out.append(fn + b"(" + str(t["id"]).encode() + b", (" + left + b"), (" + right + b"))")
            pos = t["e"]
            i += 1
        out.append(data[pos:end])
        return b"".join(out)

    new = render(0, len(data), targets)
    if new.count(b"\n") != data.count(b"\n"):
        raise RuntimeError(f"line count changed in {path_rel}")
    compile(new.decode("utf-8"), path_rel, "exec")     # must still be valid Python
    return new, len(targets)


def main():
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    shutil.copytree(src_dir, out_dir, ignore=shutil.ignore_patterns("__pycache__"))
    rows, counters = [], {"import-time": 0, "multiline-gap": 0, "chained": 0}
    nfiles = 0
    for dp, _, fns in os.walk(out_dir):
        for fn in sorted(fns):
            if not fn.endswith(".py"):
                continue
            p = os.path.join(dp, fn)
            rel = "sqlglot/" + os.path.relpath(p, out_dir).replace(os.sep, "/")
            data = open(p, "rb").read()
            new, n = convert(rel, data, rows, counters)
            if n:
                open(p, "wb").write(new)
                nfiles += 1
    json.dump({"sites": rows, "skipped": counters}, open(sites_path, "w"))
    print(f"instrumented {len(rows)} `is`/`is not` sites in {nfiles} files; skipped {counters}")


main()
