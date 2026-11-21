"""Diagnostics: compare selection strategies on the sample with the official scorer logic."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import score, selector  # noqa: E402

sample = ROOT / "sample"
tests = json.loads((sample / "tests.json").read_text())["tests"]
answers = json.loads((sample / "answers.json").read_text())["commits"]
by = {t["number"]: t for t in tests}
sel = selector.Selector(tests)


def run(name, chooser):
    lines, total, zero = [], 0, 0
    for p in sorted((sample / "commits").glob("*.patch")):
        nums = chooser(p.read_text(encoding="utf-8", errors="replace"))
        total += len(nums); zero += not nums
        lines.append(json.dumps({"commit": p.stem, "workers": selector.best_split([by[n] for n in sorted(nums)])}))
    ev = score.evaluate_run(("\n".join(lines) + "\n").encode(), tests, answers)
    print(f"{name:38s} simulated={ev['simulated_milliseconds']/1000:9.3f}s misses={len(ev['missed_commits'])} avg_selected={total/30:6.1f} zero={zero}")


def full(_):
    return set(sel.all_numbers)


def file_level(text, with_pool=False):
    """Direct file-based: every test that executes ANY line of a changed .py file; fixtures by reader."""
    files = selector.parse_patch(text) or []
    bits = 0
    for f in files:
        ent = sel.map["files"].get(f["old"])
        if ent is not None:
            bits |= sel.sets[ent["file"]]
        for p in (f["old"], f["new"]):
            if p in sel.map["fixtures"]:
                bits |= sel.sets[sel.map["fixtures"][p]]
    n = sel.numbers(bits)
    return n | sel.numbers(sel.pool_bits) if with_pool else n


run("full suite (Milestone 1 scheduler)", full)
run("direct file-level (no pool rule)", file_level)
run("direct file-level (+pool rule)", lambda t: file_level(t, True))
def hybrid(text, pool=True):
    saved = sel.pool_bits
    sel.pool_bits = saved if pool else 0
    try:
        r = sel.select(text)[0]
    finally:
        sel.pool_bits = saved
    return set(sel.all_numbers) if r is None else r


run("hybrid line-level (no pool rule)", lambda t: hybrid(t, False))
run("hybrid line-level + pool rule (final)", hybrid)
