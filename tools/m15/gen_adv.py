"""Adversarial literal arg_types mutants on NON-null profiled sites, chosen to stress inheritance (classes with
subclasses), positional from_arg_list mapping (Func subclasses: key order), import-time required_args (flag flips),
key renames and entry deletion. Seed 20261125. Keeps only mutants that M15 narrows."""
import ast, difflib, glob, gzip, json, os, random, re, sys
sys.path.insert(0, ".")
import selector
rng = random.Random(20261125)
tests = json.load(open("sample/tests.json"))["tests"]
M11 = selector.Selector(tests, clsprof_path=None); M15 = selector.Selector(tests)
P = json.load(gzip.open("clsprof_profile.json.gz", "rt"))
sites = [k for k, v in P["sites"].items() if v is not None]
# classes with subclasses / Func subclasses
subc = set(); funcs = set()
for f in glob.glob("work/sqlglot/sqlglot/expressions/*.py"):
    for n in ast.walk(ast.parse(open(f, encoding="utf-8").read())):
        if isinstance(n, ast.ClassDef):
            for b in n.bases:
                nm = b.id if isinstance(b, ast.Name) else getattr(b, "attr", None)
                if nm: subc.add(nm)
                if nm == "Func": funcs.add(n.name)
def cls_of(path, line):
    t = ast.parse(open("work/sqlglot/" + path, encoding="utf-8").read())
    for n in ast.walk(t):
        if isinstance(n, ast.ClassDef) and n.lineno <= line <= n.end_lineno:
            best = n
    return best.name
ENTRY = re.compile(r'^(\s*)"([A-Za-z_]+)":\s*(True|False)\s*,\s*$')
rng.shuffle(sites); out = "work/m15/adv"; os.makedirs(out, exist_ok=True); idx = {}; k = 0
want = {"flip-inherited": 3, "flip-func": 3, "rename-key": 3, "delete-entry": 3, "swap-order": 3}
got = {x: 0 for x in want}
for key in sites:
    path, s, e = key.rsplit(":", 2); s, e = int(s), int(e)
    if e - s < 2: continue
    lines = open("work/sqlglot/" + path, encoding="utf-8").read().split("\n")
    ent = [i for i in range(s, e - 1) if ENTRY.match(lines[i])]          # 0-based indexes of entry lines
    if len(ent) < 2: continue
    c = cls_of(path, s)
    ops = []
    if c in subc: ops.append("flip-inherited")
    if c in funcs: ops += ["flip-func", "swap-order"]
    ops += ["rename-key", "delete-entry"]
    rng.shuffle(ops)
    for op in ops:
        if got[op] >= want[op]: continue
        nl = list(lines); i = rng.choice(ent); m = ENTRY.match(nl[i])
        if op.startswith("flip"): nl[i] = '%s"%s": %s,' % (m.group(1), m.group(2), "False" if m.group(3) == "True" else "True")
        elif op == "rename-key": nl[i] = '%s"%s_x": %s,' % (m.group(1), m.group(2), m.group(3))
        elif op == "delete-entry": nl[i] = m.group(1) + '"__removed__": False,' if False else None
        if op == "delete-entry": del nl[i]
        if op == "swap-order":
            j = ent[ent.index(i) + 1] if ent.index(i) + 1 < len(ent) else ent[ent.index(i) - 1]
            nl[i], nl[j] = nl[j], nl[i]
        body = list(difflib.unified_diff(lines, nl, "a/" + path, "b/" + path, n=3, lineterm=""))
        txt = "diff --git a/%s b/%s\n" % (path, path) + "\n".join(body) + "\n"
        a, _ = M11.select(txt); b, _ = M15.select(txt)
        if a is None or b is None or a == b: continue
        pid = "a%02d" % k; k += 1; got[op] += 1
        open(os.path.join(out, pid + ".patch"), "w", encoding="utf-8", newline="\n").write(txt)
        idx[pid] = {"site": key, "class": c, "op": op, "m11": len(a), "m15": len(b)}
        break
    if all(got[x] >= want[x] for x in want): break
json.dump(idx, open(os.path.join(out, "index.json"), "w", newline="\n"), indent=1)
for p, v in idx.items(): print(p, v)
