"""Map-build time: find tests that run `python -c <code>` in a subprocess (the code is a string
literal in the pinned test source) and write the snippets to <outdir>/<n>.py plus index.json.
They are then traced with coverage (tools/trace_subprocess.sh), so the test gets real line
coverage instead of an always-run rule. Tests whose code cannot be extracted stay always-run."""
import ast, json, os, sys
repo, outdir = sys.argv[1], sys.argv[2]
os.makedirs(outdir, exist_ok=True)
index = {}
for dp, _, fns in os.walk(os.path.join(repo, "tests")):
    for fn in fns:
        if not fn.endswith(".py"):
            continue
        full = os.path.join(dp, fn)
        src = open(full, encoding="utf-8").read()
        if "subprocess" not in src:
            continue
        rel = os.path.relpath(full, repo).replace(os.sep, "/")
        tree = ast.parse(src)
        for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
            for m in (n for n in cls.body if isinstance(n, ast.FunctionDef)):
                uses = any(isinstance(x, ast.Name) and x.id == "subprocess" for x in ast.walk(m))
                if not uses:
                    continue
                codes = [a.value.value for a in ast.walk(m)
                         if isinstance(a, ast.Assign) and len(a.targets) == 1
                         and isinstance(a.targets[0], ast.Name) and a.targets[0].id == "code"
                         and isinstance(a.value, ast.Constant) and isinstance(a.value.value, str)]
                if len(codes) == 1:
                    n = len(index)
                    with open(os.path.join(outdir, f"{n}.py"), "w", newline="\n") as f:
                        f.write(codes[0] + "\n")
                    index[f"{rel}::{cls.name}::{m.name}"] = n
json.dump(index, open(os.path.join(outdir, "index.json"), "w"), indent=1)
print(index)
