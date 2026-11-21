#!/usr/bin/env python3
"""Conservative-fallback checks for the identity-swap profile (Milestone 8).
Reference = the Milestone 7 selector read from git (d6a38b9), untouched. Checks:
  1. profile disabled  => selections identical to M7 on every patch corpus
  2. missing/empty/garbage/wrong-version/stale-sha/truncated profile => identical to M7
  3. profile enabled   => never selects a test M7 would not (subset), and differs only for pure identity swaps
  4. shapes the profile must never narrow (reverse swap, `is`->`!=`, swap+other edit, other edits) => identical to M7
Usage: check_fallback.py [--corpus DIR ...]
"""
import difflib, glob, gzip, importlib.util, json, os, re, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import selector as NEW

tmp = Path(tempfile.mkdtemp())
(tmp / "selector.py").write_text(subprocess.check_output(["git", "show", "d6a38b9:selector.py"], cwd=ROOT).decode("utf-8"), encoding="utf-8")
(tmp / "selector_map.json.gz").write_bytes((ROOT / "selector_map.json.gz").read_bytes())
spec = importlib.util.spec_from_file_location("m7sel", tmp / "selector.py")
M7 = importlib.util.module_from_spec(spec); spec.loader.exec_module(M7)

tests = json.load(open(ROOT / "sample/tests.json"))["tests"]
old = M7.Selector(tests)
prof = ROOT / "isprof_profile.json.gz"
off = NEW.Selector(tests, profile_path=None)
on = NEW.Selector(tests, profile_path=prof)
SQLGLOT = ROOT / "work/sqlglot"

corpora = {"sample": ROOT / "sample/commits", "heldout1": ROOT / "work/isprof/heldout",
           "heldout2": ROOT / "work/isprof/heldout2", "mutations": ROOT / "work/mutations"}
patches = {}
for name, d in corpora.items():
    for p in sorted(glob.glob(str(d / "*.patch"))):
        patches[f"{name}/{os.path.basename(p)}"] = open(p, encoding="utf-8", errors="replace").read()
print("patches:", len(patches))
fail = 0
def sel(s, t):
    n, why = s.select(t)
    return None if n is None else frozenset(n), why
def check(label, cond, extra=""):
    global fail
    if not cond:
        fail += 1
        print("FAIL", label, extra)

# 1. profile disabled == M7
for k, t in patches.items():
    check("1:" + k, sel(off, t) == sel(old, t))
print("1. profile disabled identical to M7:", fail == 0)

# 2. bad profiles
bad = {}
d = tmp / "badprof"; d.mkdir()
good = json.load(gzip.open(prof, "rt"))
def w(name, obj=None, raw=None):
    p = d / name
    if raw is not None: p.write_bytes(raw)
    else:
        with gzip.open(p, "wt") as f: json.dump(obj, f)
    return p
bad["missing"] = d / "nope.json.gz"
bad["empty"] = w("empty.gz", raw=b"")
bad["garbage"] = w("garbage.gz", raw=os.urandom(200))
bad["not-gzip-json"] = w("txt.gz", raw=b"{}")
bad["wrong-version"] = w("ver.gz", dict(good, version=2))
bad["stale-sha"] = w("sha.gz", dict(good, tests_sha="0" * 40))
raw = (ROOT / "isprof_profile.json.gz").read_bytes()
bad["truncated"] = w("trunc.gz", raw=raw[: len(raw) // 2])
bad["missing-keys"] = w("keys.gz", {"version": 1, "tests_sha": good["tests_sha"]})
bad["bad-hex"] = w("hex.gz", dict(good, sets=["zz"] + good["sets"][1:]))
f0 = fail
for name, p in bad.items():
    s = NEW.Selector(tests, profile_path=p)
    for k, t in patches.items():
        check(f"2:{name}:{k}", sel(s, t) == sel(old, t))
print("2. corrupt/stale/missing profiles identical to M7:", fail == f0, f"({len(bad)} variants x {len(patches)} patches)")

# 3. enabled: subset, and where it differs the patch is a pure identity swap
diff_keys = []
f0 = fail
for k, t in patches.items():
    a, b = sel(old, t), sel(on, t)
    if a[0] is None:                 # M7 runs everything: any narrower answer is still a subset
        if b[0] is not None: diff_keys.append(k)
        continue
    check("3-not-wider:" + k, b[0] is not None and b[0] <= a[0])
    if b[0] is not None and b[0] != a[0]: diff_keys.append(k)
print("3. enabled selection is a subset of M7; differs on", len(diff_keys), "patches:", fail == f0)
for k in diff_keys:
    files = NEW.parse_patch(patches[k])
    ok = all(f["status"] == "modified" and f["old"].startswith("sqlglot/") and all(
        len(rem) == 1 and len(add) == 1 and NEW.Selector._identity_swap_kind(rem[0][1], add[0]) for _, rem, add in f["blocks"])
        for f in files)
    check("3-pure-swap:" + k, ok)

# 4. shapes that must not narrow (derived from held-out patches that DID narrow)
def reverse(t):
    out = []
    for line in t.split("\n"):
        if line.startswith("--- a/"): out.append(line)
        elif line.startswith("+++ b/"): out.append(line)
        elif line.startswith("-") and not line.startswith("---"): out.append("+" + line[1:])
        elif line.startswith("+") and not line.startswith("+++"): out.append("-" + line[1:])
        else: out.append(line)
    return "\n".join(out)
def rebuild(t, fn):
    out = []
    for line in t.split("\n"):
        out.append(fn(line))
    return "\n".join(out)
shapes = 0; f0 = fail
for k in diff_keys:
    t = patches[k]
    variants = {
        "reverse-swap": reverse(t),
        "is->is-not": rebuild(t, lambda l: re.sub(r"(?<![\w=!])(==|!=) ", "is not ", l, count=1) if l.startswith("+") and not l.startswith("+++") else l),
        "swap-to-other-op": rebuild(t, lambda l: (l.replace("==", "!=", 1) if "==" in l else l.replace("!=", "==", 1)) if l.startswith("+") and not l.startswith("+++") else l),
        "swap+comment-text": rebuild(t, lambda l: l + "  # x" if l.startswith("+") and not l.startswith("+++") else l),
    }
    for name, v in variants.items():
        shapes += 1
        check(f"4:{name}:{k}", sel(on, v) == sel(old, v))
# swap + an unrelated second edit in the same file
j = 0
for k in diff_keys[:12]:
    m = re.search(r"^diff --git a/(\S+) b/", patches[k], re.M)
    path = m.group(1)
    src = open(SQLGLOT / path, encoding="utf-8", newline="").read().split("\n")
    sw = NEW.parse_patch(patches[k])[0]["blocks"][0][1][0][0]
    new = list(src)
    nl = src[sw - 1]
    new[sw - 1] = re.sub(r"\bis not\b", "!=", nl, 1) if " is not " in nl else re.sub(r"\bis\b", "==", nl, 1)
    other = next((i for i, l in enumerate(src) if abs(i - (sw - 1)) > 12 and ("True" in l or "False" in l) and "#" not in l), None)
    if other is None: continue
    new[other] = new[other].replace("True", "False", 1) if "True" in new[other] else new[other].replace("False", "True", 1)
    body = list(difflib.unified_diff(src, new, f"a/{path}", f"b/{path}", n=3, lineterm=""))
    t = f"diff --git a/{path} b/{path}\n" + "\n".join(body) + "\n"
    shapes += 1
    check(f"4:swap+other-edit:{k}", sel(on, t) == sel(old, t))
print("4. non-narrowable shapes identical to M7:", fail == f0, f"({shapes} variants from {len(diff_keys)} narrowed patches)")
print("RESULT", "PASS" if fail == 0 else f"FAIL ({fail})")
sys.exit(1 if fail else 0)
