#!/usr/bin/env python3
"""Local diagnostics only: runs selector.Selector on sample patches and scores with score.py.
Answers are read here for *evaluation*; the selector never sees them.
Usage: python tools/evaluate.py [sample_dir]
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import score  # noqa: E402
import selector  # noqa: E402

sample = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "sample"
tests = json.loads((sample / "tests.json").read_text())["tests"]
answers = json.loads((sample / "answers.json").read_text())["commits"]
by_number = {t["number"]: t for t in tests}
t0 = time.process_time()
sel = selector.Selector(tests)
load_s = time.process_time() - t0

lines, rows = [], []
t0 = time.process_time()
for p in sorted((sample / "commits").glob("*.patch")):
    nums, why = sel.select(p.read_text(encoding="utf-8", errors="replace"))
    if nums is None:
        nums = set(sel.all_numbers)
    ws = selector.best_split([by_number[n] for n in sorted(nums)])
    lines.append(json.dumps({"commit": p.stem, "workers": ws}))
    fail = set(answers[p.stem]["failing"])
    rows.append((p.stem, answers[p.stem]["kind"], len(nums), why, sorted(fail - nums)))
sel_s = time.process_time() - t0
ev = score.evaluate_run(("\n".join(lines) + "\n").encode(), tests, answers)
print(f"map load {load_s:.2f}s, selection {sel_s:.2f}s CPU")
print("simulated", ev["simulated_milliseconds"] / 1000, "misses", ev["missed_commits"])
kinds = {}
for c, k, n, why, missed in rows:
    print(f"{c} {k:8s} selected={n:5d} {why:10s} missed={missed}")
    d = kinds.setdefault(k, [0, 0, 0])
    d[0] += 1; d[1] += n; d[2] += (n == 0)
print("zero-test selections:", sum(r[2] == 0 for r in rows))
for k, (c, n, z) in kinds.items():
    print(f"  {k}: commits={c} avg_selected={n / c:.0f} zero={z}")
