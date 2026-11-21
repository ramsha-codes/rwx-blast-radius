"""Blast-radius selector: pick the tests a patch can break, then schedule them.

1. Parse each unified diff (changed files and changed *old-file* lines; the patches
   are against the pinned sqlglot commit, so old line numbers index our map).
2. Look the lines up in selector_map.json.gz, which was built from the pinned commit
   only (per-test line coverage + class-instantiation + fixture-open traces; see
   tools/ and MILESTONE2.md). No patch -> answer tables exist anywhere.
3. Anything the map cannot explain falls back to a wider (ultimately: all) test set.
4. Schedule the selected tests with the Milestone 1 LPT scheduler over 1..8 workers.
"""

import gzip
import json
import re
import sys
from pathlib import Path

DATA = Path("/data")
MAP_PATH = Path(__file__).with_name("selector_map.json.gz")
MAX_WORKERS = 8
# Tests that fan out to spawned ProcessPoolExecutor children used to be always-run (Milestone 2)
# because coverage could not see the children. The Milestone 3 map traces the children, so the
# blanket rule is off; flip this to True for a conservative build.
POOL_RULE = False
# Uncertainty-aware fallback: if the changed code is executed by at least this fraction of the
# suite, run everything. Such a set is almost the whole suite anyway, and breaking a very central
# line can also fail test files at collection time (which per-test coverage cannot attribute).
CENTRAL_FRACTION = 0.8
WORKER_COST_MS = 2000  # SCORING.md: every non-empty worker adds 2 s

# Paths that cannot influence a test run (docs, packaging metadata, benchmarks...).
INERT_PREFIXES = ("posts/", "pdoc/", "benchmarks/", "sqlglot-integration-tests/",
                  ".github/", "docs/")
# sqlglotc/ is NOT inert: tests/test_sqlglotc.py executes sqlglotc/setup.py via runpy, and line coverage
# of the pinned run does not attribute that file. Any non-doc change under it selects that test file.
SQLGLOTC_PREFIX = "sqlglotc/"
SQLGLOTC_TEST_FILE = "tests/test_sqlglotc.py"
INERT_SUFFIXES = (".md", ".rst", ".txt", ".png", ".jpg", ".svg", ".typed")
INERT_NAMES = {"LICENSE", ".gitignore", "MANIFEST.in", "CHANGELOG.md", "py.typed"}


def duration_ms(test: dict) -> int:
    """Same rounding as the scorer (halves up)."""
    return int(test["seconds"] * 1000 + 0.5)


# --------------------------------------------------------------------------- scheduling
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


# --------------------------------------------------------------------------- diff parsing
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _unquote(path: str) -> str:
    path = path.strip()
    if path.startswith('"') and path.endswith('"'):
        try:
            path = json.loads(path)
        except ValueError:
            path = path[1:-1]
    return path


def parse_patch(text: str) -> list[dict] | None:
    """Return [{old, new, status, blocks:[(old_line_before, [removed], [added])], binary}]
    or None when the patch is not understood (caller must fall back to ALL)."""
    files: list[dict] = []
    cur = None
    old_no = 0
    block = None
    in_hunk = False

    def flush():
        nonlocal block
        if block is not None and cur is not None and (block[1] or block[2]):
            cur["blocks"].append(tuple(block))
        block = None

    for line in text.split("\n"):
        if line.startswith("diff --git "):
            flush()
            in_hunk = False
            m = re.match(r'^diff --git (a/.+|"a/.+") (b/.+|"b/.+")$', line)
            if not m:
                return None
            cur = {"old": _unquote(m.group(1))[2:], "new": _unquote(m.group(2))[2:],
                   "status": "modified", "blocks": [], "binary": False}
            files.append(cur)
            continue
        if cur is None:
            continue
        if not in_hunk:
            if line.startswith("new file mode"):
                cur["status"] = "added"
            elif line.startswith("deleted file mode"):
                cur["status"] = "deleted"
            elif line.startswith("rename from "):
                cur["status"] = "renamed"
                cur["old"] = _unquote(line[len("rename from "):])
            elif line.startswith("rename to "):
                cur["new"] = _unquote(line[len("rename to "):])
            elif line.startswith("copy from ") or line.startswith("copy to "):
                cur["status"] = "renamed"
            elif line.startswith("Binary files") or line.startswith("GIT binary patch"):
                cur["binary"] = True
            elif line.startswith("--- "):
                if line.startswith("--- /dev/null"):
                    cur["status"] = "added"
            elif line.startswith("+++ "):
                if line.startswith("+++ /dev/null"):
                    cur["status"] = "deleted"
            elif line.startswith("@@"):
                pass
        m = HUNK.match(line)
        if m:
            flush()
            old_no = int(m.group(1))
            if m.group(2) == "0":
                old_no += 1        # "-N,0" means insertion *after* line N
            in_hunk = True
            block = None
            continue
        if not in_hunk:
            continue
        if line.startswith("\\"):
            continue
        tag = line[:1]
        if tag == " ":
            flush()
            old_no += 1
        elif tag == "-":
            if block is None:
                block = [old_no - 1, [], []]
            block[1].append((old_no, line[1:]))
            old_no += 1
        elif tag == "+":
            if block is None:
                block = [old_no - 1, [], []]
            block[2].append(line[1:])
        elif line == "":
            # blank context line whose leading space was stripped by a tool
            flush()
            old_no += 1
        else:
            return None
    flush()
    return files or None


# --------------------------------------------------------------------------- the map
class Selector:
    def __init__(self, tests: list[dict], map_path: Path = MAP_PATH):
        with gzip.open(map_path, "rt", encoding="utf-8") as f:
            m = json.load(f)
        self.map = m
        self.sets = [int(h, 16) if h else 0 for h in m["sets"]]
        by_id = {t["id"]: t["number"] for t in tests}
        # map bit i -> test number in the given tests.json
        self.bit_to_number = [by_id.get(i) for i in m["tests"]]
        mapped_ids = set(m["tests"])
        self.extra_always = sorted(t["number"] for t in tests if t["id"] not in mapped_ids)
        self.unmapped_bits = 0
        for i in m["unmapped_tests"]:
            self.unmapped_bits |= 1 << i
        self.pool_bits = 0
        if POOL_RULE:
            for i in m.get("pool_tests", []):
                self.pool_bits |= 1 << i
        # tests that start a fresh interpreter (subprocess): coverage cannot attribute that
        # process to the test, so they run whenever production code changed (they are cheap)
        self.proc_bits = 0
        for i in m.get("proc_tests", []):
            self.proc_bits |= 1 << i
        self.all_bits = (1 << len(m["tests"])) - 1
        self.all_numbers = [t["number"] for t in tests]

    # -- helpers
    def numbers(self, bits: int) -> set[int]:
        out = set()
        i = 0
        while bits:
            if bits & 1 and self.bit_to_number[i] is not None:
                out.add(self.bit_to_number[i])
            bits >>= 1
            i += 1
        return out

    @staticmethod
    def _comment_or_blank(s: str) -> bool:
        t = s.strip()
        return t == "" or t.startswith("#")

    def _file_bits(self, f: dict) -> tuple[int, bool] | None:
        """(bits, code_changed) for one changed .py file, or None meaning 'cannot tell: ALL'.
        code_changed: some non-comment line was touched (the pool tests then must run)."""
        status = f["status"]
        mp = self.map
        old, new = f["old"], f["new"]
        bits = 0
        code = status in ("deleted", "renamed")
        if status in ("deleted", "renamed"):
            # the module disappears: everything that used it can break
            for p in {old, new}:
                ent = mp["files"].get(p)
                if ent is not None:
                    bits |= self.sets[ent["file"]]
        ent = mp["files"].get(old)
        if ent is None:
            # Unknown .py file. Only a brand-new test module (never numbered in tests.json and
            # imported by nothing) is provably inert; a new/unknown module under sqlglot/ could
            # be picked up by package init, lazy dialect loading or directory-scanning tests,
            # and conftest.py / setup scripts affect everything. All of those -> run all.
            base = new.rsplit("/", 1)[-1]
            if (status == "added" and new.startswith("tests/") and base.startswith("test_")):
                return bits, code
            return None
        if status == "added":
            return None
        n = ent["n"]
        spans = ent["strspans"]
        for before, removed, added in f["blocks"]:
            for lineno, _ in removed:
                if not 1 <= lineno <= n:
                    return None
                bits |= self.sets[ent["l2s"][lineno]]
            added_code = [x for x in added if not self._comment_or_blank(x)]
            removed_code = [x for _, x in removed if not self._comment_or_blank(x)]
            in_string = any(s <= before and before + 1 <= e for s, e in spans)
            code = code or bool(added_code or removed_code) or (in_string and bool(added))
            if added and (added_code or True):
                if not added_code:
                    # comment/blank-only addition: harmless unless inside a string literal
                    if any(s <= before and before + 1 <= e for s, e in spans):
                        pass
                    else:
                        continue
                elif removed_code and len(added) <= len(removed):
                    continue      # in-place edit: the replaced lines' sets already apply
                p = removed[-1][0] if removed else before
                if not 0 <= p <= n:
                    return None
                bits |= self.sets[ent["ins"][p]]
        return bits, code

    def select(self, text: str) -> tuple[set[int] | None, str]:
        """Returns (test numbers, reason); numbers None means 'run everything'."""
        files = parse_patch(text)
        if files is None:
            return None, "unparsed"
        mp = self.map
        bits = 0
        prod_code = False
        for f in files:
            names = {f["old"], f["new"]}
            if any(p.startswith(SQLGLOTC_PREFIX) and not p.endswith(INERT_SUFFIXES) for p in names):
                ent = mp["files"].get(SQLGLOTC_TEST_FILE)
                if ent is None:
                    return None, "sqlglotc-unmapped"
                bits |= self.sets[ent["file"]]
                continue
            if all(self._inert(p) for p in names):
                continue
            if f["binary"]:
                return None, "binary"
            if any(p.startswith("tests/fixtures/") for p in names):
                for p in names:          # renamed/deleted fixtures break the same readers
                    if p in mp["fixtures"]:
                        bits |= self.sets[mp["fixtures"][p]]
                continue
            if f["old"].endswith(".py") or f["new"].endswith(".py"):
                res = self._file_bits(f)
                if res is None:
                    return None, "py-unmapped"
                bits |= res[0]
                if res[1] and (f["old"].startswith("sqlglot/") or f["new"].startswith("sqlglot/")):
                    prod_code = True
                continue
            return None, "other-file"
        if bin(bits).count("1") >= CENTRAL_FRACTION * len(self.map["tests"]):
            return None, "central"
        numbers = self.numbers(bits)
        if prod_code:
            # Tests that farm work out to spawned ProcessPoolExecutor children are invisible to
            # line coverage: always run them when production code changed.
            numbers |= self.numbers(self.pool_bits) | self.numbers(self.proc_bits)
        if bits:
            numbers |= self.numbers(self.unmapped_bits) | set(self.extra_always)
        return numbers, "map"

    @staticmethod
    def _inert(path: str) -> bool:
        name = path.rsplit("/", 1)[-1]
        return (path.startswith(INERT_PREFIXES) or path.endswith(INERT_SUFFIXES)
                or name in INERT_NAMES) and not path.startswith("tests/")


# --------------------------------------------------------------------------- main
def main() -> None:
    tests = json.loads((DATA / "tests.json").read_text())["tests"]
    by_number = {t["number"]: t for t in tests}
    sel = Selector(tests)
    cache: dict[tuple, list[list[int]]] = {}
    total = 0
    zero = 0
    for patch in sorted((DATA / "commits").glob("*.patch")):
        try:
            text = patch.read_text(encoding="utf-8", errors="replace")
            numbers, reason = sel.select(text)
        except Exception as exc:  # never crash: fall back to the full suite
            print(f"{patch.stem}: selector error {exc!r}; running all", file=sys.stderr)
            numbers, reason = None, "error"
        if numbers is None:
            numbers = set(sel.all_numbers)
        key = tuple(sorted(numbers))
        if key not in cache:
            cache[key] = best_split([by_number[n] for n in key])
        total += len(numbers)
        zero += not numbers
        print(json.dumps({"commit": patch.stem, "workers": cache[key]}))
        print(f"{patch.stem}: {len(numbers)} tests ({reason})", file=sys.stderr)
    print(f"selected {total} tests in total, {zero} empty commits", file=sys.stderr)


if __name__ == "__main__":
    main()
