#!/usr/bin/env python3
"""Generate seeded mutation patches of the pinned sqlglot checkout (validation only).

Each patch is a standalone unified diff against the pinned commit (same shape as the
contest patches). Mutation kinds: operator/constant flips in production code, inserted
statements, deleted statements, comment-only additions, fixture edits, and multi-file combos.
The checkout is never modified; patches are produced with difflib.

Usage: python tools/mutate.py --repo work/sqlglot --out work/mutations --n 60 --seed 7
Output: <out>/<id>.patch and <out>/index.json (id -> kind, files). Index is for reporting
only; nothing here is ever read by the selector.
"""
import argparse
import ast
import difflib
import json
import os
import random
import re

ap = argparse.ArgumentParser()
ap.add_argument("--repo", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--n", type=int, default=60)
ap.add_argument("--seed", type=int, default=7)
a = ap.parse_args()
rng = random.Random(a.seed)

# (regex, replacement) single-site token mutations. Applied to one occurrence on one line.
OPS = [
    (r" == ", " != "), (r" != ", " == "), (r" is not ", " is "), (r" is None", " is not None"),
    (r" and ", " or "), (r" or ", " and "), (r" < ", " <= "), (r" > ", " >= "),
    (r" <= ", " < "), (r" >= ", " > "), (r" \+ ", " - "), (r" - ", " + "),
    (r"\bTrue\b", "False"), (r"\bFalse\b", "True"), (r"\bnot ", ""),
    (r"\bif (\w)", r"if not \1"), (r"return ([\w\.]+)$", "return None"),
    (r"\b(\d+)\b(?!\.)", lambda m: str(int(m.group(1)) + 1)),
    (r" in \(", " not in ("), (r"\.pop\(", ".get("), (r"copy=True", "copy=False"),
    (r"copy=False", "copy=True"), (r"\bany\(", "all("), (r"\ball\(", "any("),
    (r"\[0\]", "[-1]"), (r"\[-1\]", "[0]"),
]


def read(path):
    with open(os.path.join(a.repo, path), encoding="utf-8", newline="") as f:
        return f.read()


def diff(path, old, new):
    a_l = old.split("\n")
    b_l = new.split("\n")
    body = list(difflib.unified_diff(a_l, b_l, f"a/{path}", f"b/{path}", n=3, lineterm=""))
    return f"diff --git a/{path} b/{path}\n" + "\n".join(body) + "\n"


def py_files():
    out = []
    for dp, _, fns in os.walk(os.path.join(a.repo, "sqlglot")):
        for fn in sorted(fns):
            if fn.endswith(".py"):
                out.append(os.path.relpath(os.path.join(dp, fn), a.repo).replace(os.sep, "/"))
    return sorted(out)


FILES = py_files()
SIZES = {p: len(read(p).split("\n")) for p in FILES}
FIXTURES = []
for dp, _, fns in os.walk(os.path.join(a.repo, "tests", "fixtures")):
    for fn in sorted(fns):
        if fn.endswith(".sql"):
            FIXTURES.append(os.path.relpath(os.path.join(dp, fn), a.repo).replace(os.sep, "/"))
FIXTURES.sort()


def valid(src):
    try:
        ast.parse(src)
        return True
    except SyntaxError:
        return False


def code_lines(lines):
    """Indices of plain code lines (not blank/comment/string-ish) worth mutating."""
    return [i for i, l in enumerate(lines)
            if l.strip() and not l.strip().startswith(("#", '"""', "'''", "@", "import ", "from "))]


def mutate_code(path):
    src = read(path)
    lines = src.split("\n")
    cands = code_lines(lines)
    rng.shuffle(cands)
    for i in cands[:400]:
        ops = OPS[:]
        rng.shuffle(ops)
        for pat, rep in ops:
            if re.search(pat, lines[i]):
                new_line = re.sub(pat, rep, lines[i], count=1)
                if new_line == lines[i]:
                    continue
                new = lines[:i] + [new_line] + lines[i + 1:]
                if valid("\n".join(new)):
                    return "\n".join(new), f"op:{pat}"
    return None, None


def insert_stmt(path):
    src = read(path)
    lines = src.split("\n")
    cands = [i for i in code_lines(lines) if lines[i].startswith("        ") and
             not lines[i].rstrip().endswith((":", ",", "(", "[", "{", "\\"))]
    rng.shuffle(cands)
    for i in cands[:200]:
        indent = re.match(r"\s*", lines[i]).group(0)
        kind = rng.choice(["noop", "early_return_none"])
        stmt = f"{indent}_unused_marker = 0" if kind == "noop" else f"{indent}return None"
        new = lines[:i + 1] + [stmt] + lines[i + 1:]
        if valid("\n".join(new)):
            return "\n".join(new), f"insert:{kind}"
    return None, None


def delete_stmt(path):
    src = read(path)
    lines = src.split("\n")
    cands = [i for i in code_lines(lines) if lines[i].startswith("        ") and
             not lines[i].rstrip().endswith((":", ",", "(", "[", "{", "\\", ")", "]", "}"))]
    rng.shuffle(cands)
    for i in cands[:200]:
        new = lines[:i] + lines[i + 1:]
        if valid("\n".join(new)):
            return "\n".join(new), "delete"
    return None, None


def add_comment(path):
    lines = read(path).split("\n")
    cands = [i for i in code_lines(lines) if lines[i].startswith("    ")]
    i = rng.choice(cands)
    indent = re.match(r"\s*", lines[i]).group(0)
    new = lines[:i] + [f"{indent}# note: keep this in sync"] + lines[i:]
    return "\n".join(new), "comment"


def mutate_fixture(path):
    src = read(path)
    lines = src.split("\n")
    cands = [i for i, l in enumerate(lines) if l.strip() and not l.startswith(("--", "#"))
             and re.search(r"[A-Za-z0-9]", l)]
    i = rng.choice(cands)
    l = lines[i]
    m = list(re.finditer(r"\d+", l))
    if m and rng.random() < 0.6:
        s = rng.choice(m)
        nl = l[:s.start()] + str(int(s.group(0)) + 1) + l[s.end():]
    else:
        kws = list(re.finditer(r"\b(AND|OR|ASC|DESC|LEFT|INNER|MAX|MIN|SUM|COUNT)\b", l))
        if kws:
            s = rng.choice(kws)
            swap = {"AND": "OR", "OR": "AND", "ASC": "DESC", "DESC": "ASC", "LEFT": "INNER",
                    "INNER": "LEFT", "MAX": "MIN", "MIN": "MAX", "SUM": "COUNT", "COUNT": "SUM"}
            nl = l[:s.start()] + swap[s.group(0)] + l[s.end():]
        else:
            nl = l + " "
    new = lines[:i] + [nl] + lines[i + 1:]
    return "\n".join(new), "fixture"


def weighted_file():
    return rng.choices(FILES, weights=[SIZES[p] for p in FILES])[0]


# distribution loosely mirroring the public sample: mostly code edits, some fixture,
# some multi, a few comments, plus insertion/deletion
KINDS = (["code"] * 24 + ["fixture"] * 10 + ["multi"] * 6 + ["comment"] * 4 +
         ["insert"] * 4 + ["delete"] * 4)

index = {}
os.makedirs(a.out, exist_ok=True)
n = 0
attempts = 0
while n < a.n and attempts < a.n * 20:
    attempts += 1
    kind = rng.choice(KINDS)
    parts = []
    if kind == "code":
        p = weighted_file(); new, d = mutate_code(p)
        if new:
            parts.append((p, new, d))
    elif kind == "insert":
        p = weighted_file(); new, d = insert_stmt(p)
        if new:
            parts.append((p, new, d))
    elif kind == "delete":
        p = weighted_file(); new, d = delete_stmt(p)
        if new:
            parts.append((p, new, d))
    elif kind == "comment":
        p = weighted_file(); new, d = add_comment(p)
        parts.append((p, new, d))
    elif kind == "fixture":
        p = rng.choice(FIXTURES); new, d = mutate_fixture(p)
        parts.append((p, new, d))
    elif kind == "multi":
        p1 = weighted_file(); n1, d1 = mutate_code(p1)
        p2 = rng.choice(FIXTURES); n2, d2 = mutate_fixture(p2)
        if n1:
            parts += [(p1, n1, d1), (p2, n2, d2)]
    if not parts:
        continue
    text = "".join(diff(p, read(p), new) for p, new, _ in parts)
    mid = f"m{n:03d}"
    with open(os.path.join(a.out, mid + ".patch"), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    index[mid] = {"kind": kind, "files": [p for p, _, _ in parts], "desc": [d for _, _, d in parts]}
    n += 1
with open(os.path.join(a.out, "index.json"), "w") as f:
    json.dump(index, f, indent=1)
import collections
print(n, "mutations", dict(collections.Counter(v["kind"] for v in index.values())))
