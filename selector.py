"""The starter selector: run every test on every commit, scheduled over the best worker count (1-8).

It never misses a failing test and it is slow. Everything you do from here
is deciding which tests a change cannot break.
"""

import json
import sys
from pathlib import Path

DATA = Path("/data")
MAX_WORKERS = 8
WORKER_COST_MS = 2000  # SCORING.md: every non-empty worker adds 2 s


def duration_ms(test: dict) -> int:
    """Same rounding as the scorer (halves up)."""
    return int(test["seconds"] * 1000 + 0.5)


def split(tests: list[dict], worker_count: int) -> list[list[int]]:
    """LPT: longest test first onto the least-loaded worker (ties: lowest index)."""
    workers: list[list[int]] = [[] for _ in range(worker_count)]
    loads = [0] * worker_count
    for test in sorted(tests, key=lambda t: (-duration_ms(t), t["number"])):
        lightest = loads.index(min(loads))
        workers[lightest].append(test["number"])
        loads[lightest] += duration_ms(test)
    return workers


def best_split(tests: list[dict]) -> list[list[int]]:
    """Try 1..MAX_WORKERS workers; keep the one minimising busiest load + 2 s per worker."""
    if not tests:
        return []
    by_number = {t["number"]: duration_ms(t) for t in tests}
    best, best_cost = [], None
    for count in range(1, min(MAX_WORKERS, len(tests)) + 1):
        candidate = split(tests, count)
        cost = max(sum(by_number[n] for n in w) for w in candidate) + WORKER_COST_MS * count
        if best_cost is None or cost < best_cost:
            best, best_cost = candidate, cost
    return best


def main() -> None:
    tests = json.loads((DATA / "tests.json").read_text())["tests"]
    workers = best_split(tests)
    for patch in sorted((DATA / "commits").glob("*.patch")):
        print(json.dumps({"commit": patch.stem, "workers": workers}))
    print(f"selected {len(tests)} tests on every commit", file=sys.stderr)


if __name__ == "__main__":
    main()
