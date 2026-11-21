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
# Operand-observation profile (tools/isprof/, MILESTONE8.md): a baseline execution artifact recorded from the
# PINNED commit only. For each `a is b` / `a is not b` site it stores the tests in which every observed operand
# pair was of a type with builtin equality AND identity agreed with equality. It lets a patch that merely
# swaps `is`->`==` (or `is not`->`!=`) at such a site skip the tests for which the swap is unobservable.
# Missing/invalid/stale profile => coverage-only selection (the Milestone 7 behaviour).
PROFILE_PATH = Path(__file__).with_name("isprof_profile.json.gz")
# Query-level micro-check of test_execute_tpcds (M18/M19). Build-time artifacts from the PINNED commit only:
# pristine/ (pinned sqlglot sources + test helpers + TPC-DS fixtures) and a per-query profile (which TPC-DS queries
# execute each line; shared/import/first-touch lines; pristine result fingerprints). For a patch confined to one
# function body whose changed lines are reached by at most K queries and by no shared line, the selector re-runs just
# those queries on the patched code in a resource-limited child and drops the test only if every result is identical.
# Missing/invalid artifacts, any limit, crash, difference or doubt => the test stays selected.
MICRO_PROFILE = Path(__file__).with_name("tpcds_micro_profile.json.gz")
MICRO_CHECK = Path(__file__).with_name("micro_check.py")
PRISTINE = Path(__file__).with_name("pristine")
MICRO_CPU_S = 10                 # RLIMIT_CPU of one check
MICRO_WALL_S = 20                # wall timeout of one check (process group killed)
MICRO_MEM = 2 * 1024 ** 3        # RLIMIT_AS of one check
MICRO_TOTAL_CPU_S = 60           # all checks of one batch together

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
    def __init__(self, tests: list[dict], map_path: Path = MAP_PATH, profile_path: Path | None = PROFILE_PATH):
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
        self._profile_path = profile_path
        self._profile = None          # lazily loaded; {} = disabled
        self._micro = None            # lazily loaded; {} = disabled
        self._micro_cpu = 0.0
        self.micro_log: list[str] = []
        self._num_by_id = by_id

    # -- operand-observation profile (fail closed: any doubt => no narrowing)
    def _load_profile(self) -> dict:
        if self._profile is not None:
            return self._profile
        self._profile = {}
        if self._profile_path is None:
            return self._profile
        try:
            import hashlib
            with gzip.open(self._profile_path, "rt", encoding="utf-8") as fh:
                p = json.load(fh)
            if p.get("version") != 1:
                return self._profile
            if p.get("tests_sha") != hashlib.sha1(json.dumps(self.map["tests"]).encode()).hexdigest():
                return self._profile      # profile was not built against this map's test order
            self._profile = {"sets": [int(h, 16) for h in p["sets"]], "sites": p["sites"]}
        except Exception:
            self._profile = {}
        return self._profile

    @staticmethod
    def _identity_swap_kind(old: str, new: str) -> str | None:
        """'is' / 'is not' iff `new` is `old` with exactly one `is`->`==` / `is not`->`!=` token swap and `old`
        holds exactly one `is` operator; otherwise None."""
        import io
        import tokenize
        skip = (tokenize.NEWLINE, tokenize.NL, tokenize.ENDMARKER, tokenize.INDENT, tokenize.DEDENT)
        try:
            a = [t.string for t in tokenize.generate_tokens(io.StringIO(old.strip() + "\n").readline)
                 if t.type not in skip]
            b = [t.string for t in tokenize.generate_tokens(io.StringIO(new.strip() + "\n").readline)
                 if t.type not in skip]
        except (tokenize.TokenError, IndentationError, SyntaxError):
            return None
        if a.count("is") != 1:
            return None
        i = a.index("is")
        if i + 1 < len(a) and a[i + 1] == "not":
            return "is not" if a[:i] + ["!="] + a[i + 2:] == b else None
        return "is" if a[:i] + ["=="] + a[i + 1:] == b else None

    def _identity_swap_bits(self, f: dict, ent: dict) -> int | None:
        """Narrowed test bits when EVERY changed block of this file is a pure identity<->equality swap at a
        profiled site; None (= keep the coverage bits) in every other case."""
        if f["status"] != "modified" or f["old"] != f["new"] or not f["old"].startswith("sqlglot/"):
            return None
        if not f["blocks"]:
            return None
        prof = self._load_profile()
        if not prof:
            return None
        narrowed = 0
        for _before, removed, added in f["blocks"]:
            if len(removed) != 1 or len(added) != 1:
                return None
            lineno, old = removed[0]
            if not 1 <= lineno <= ent["n"]:
                return None
            kind = self._identity_swap_kind(old, added[0])
            if kind is None:
                return None
            k = prof["sites"].get(f'{f["old"]}:{lineno}:{lineno}:0:{kind}')
            if k is None:
                return None
            narrowed |= self.sets[ent["l2s"][lineno]] & ~prof["sets"][k]
        return narrowed

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
        nb = self._identity_swap_bits(f, ent)
        if nb is not None:
            bits = nb
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
        tp = self._num_by_id.get("tests/test_executor.py::TestExecutor::test_execute_tpcds")
        if tp is not None and tp in numbers:
            try:
                if self._micro_certifies(files):
                    numbers = numbers - {tp}
                    return numbers, "map+micro"
            except Exception:          # any doubt: keep the test
                pass
        return numbers, "map"

    # --------------------------------------------------------------- tpcds micro-check (fail closed everywhere)
    def _load_micro(self) -> dict:
        if self._micro is not None:
            return self._micro
        self._micro = {}
        try:
            with gzip.open(MICRO_PROFILE, "rt", encoding="utf-8") as fh:
                p = json.load(fh)
            if (p.get("version") == 1 and p.get("pinned") == self.map.get("pinned_commit")
                    and p.get("test") in self._num_by_id and MICRO_CHECK.is_file() and (PRISTINE / "sqlglot").is_dir()
                    and isinstance(p.get("K"), int) and p["fp"] and p["narrow"] is not None):
                self._micro = p
        except Exception:
            self._micro = {}
        return self._micro

    def _micro_plan(self, files: list[dict]):
        """(rel path, patched source, query ids) when the patch is eligible, else None."""
        import ast
        if len(files) != 1:
            return None
        f = files[0]
        old = f["old"]
        if (f["status"] != "modified" or old != f["new"] or f["binary"] or not f["blocks"]
                or not old.startswith("sqlglot/") or not old.endswith(".py")):
            return None
        prof = self._load_micro()
        if not prof:
            return None
        src = (PRISTINE / old).read_text(encoding="utf-8")
        lines = src.split("\n")
        tree = ast.parse(src)
        bodies = [(n.body[0].lineno, n.end_lineno) for n in ast.walk(tree)
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        spans = []
        for n in ast.walk(tree):
            if isinstance(n, ast.stmt) and not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                b = getattr(n, "body", None)
                hi = (b[0].lineno - 1) if isinstance(b, list) and b else n.end_lineno
                spans.append((n.lineno, max(hi, n.lineno)))
        changed = set()
        new = list(lines)
        for before, removed, added in sorted(f["blocks"], key=lambda b: -b[0]):   # bottom-up keeps line numbers
            pts = [ln for ln, _ in removed] or [before, before + 1]
            for ln in pts:
                if not any(a <= ln <= b for a, b in bodies):
                    return None                        # module/class level or decorator/signature: import-sensitive
                changed.add(ln)
                for a, b in spans:
                    if a <= ln <= b:
                        changed.update(range(a, b + 1))
            for ln, txt in removed:
                if not 1 <= ln <= len(lines) or lines[ln - 1] != txt:
                    return None                        # patch does not match the pinned source
            if removed:
                new[removed[0][0] - 1:removed[-1][0]] = added
            else:
                new[before:before] = added
        rel = old[len("sqlglot/"):]
        G = set(prof["G"].get(rel, ()))
        wide = set(prof["wide"].get(rel, ()))
        narrow = prof["narrow"].get(rel, {})
        ids = set()
        for ln in changed:
            if ln in G or ln in wide:
                return None                            # shared/import/first-touch line, or reached by > K queries
            ids.update(narrow.get(str(ln), ()))
        if not ids or len(ids) > prof["K"]:
            return None
        return old, "\n".join(new), sorted(ids)

    def _micro_certifies(self, files: list[dict]) -> bool:
        import os
        import resource
        import shutil
        import signal
        import subprocess
        import tempfile
        if self._micro_cpu >= MICRO_TOTAL_CPU_S:
            return False
        plan = self._micro_plan(files)
        if plan is None:
            return False
        old, content, ids = plan
        d = tempfile.mkdtemp(prefix="mc_")
        try:
            def mirror(src: Path, dst: Path, parts: list[str]) -> None:
                dst.mkdir(exist_ok=True)
                for e in os.listdir(src):
                    if parts and e == parts[0]:
                        if len(parts) == 1:
                            (dst / e).write_text(content, encoding="utf-8")
                        else:
                            mirror(src / e, dst / e, parts[1:])
                    else:
                        os.symlink(src / e, dst / e)
            mirror(PRISTINE, Path(d), old.split("/"))

            def limits() -> None:
                resource.setrlimit(resource.RLIMIT_CPU, (MICRO_CPU_S, MICRO_CPU_S + 1))
                resource.setrlimit(resource.RLIMIT_AS, (MICRO_MEM, MICRO_MEM))
            before = resource.getrusage(resource.RUSAGE_CHILDREN)
            p = subprocess.Popen([sys.executable, str(MICRO_CHECK), str(MICRO_PROFILE), ",".join(map(str, ids))],
                                 cwd=d, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, preexec_fn=limits,
                                 start_new_session=True,
                                 env={"PYTHONPATH": d, "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1",
                                      "HOME": "/tmp", "PATH": "/usr/local/bin:/usr/bin:/bin"})
            try:
                out, _ = p.communicate(timeout=MICRO_WALL_S)
            except subprocess.TimeoutExpired:
                out = b""
            finally:
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except OSError:
                    pass
                p.wait()
                after = resource.getrusage(resource.RUSAGE_CHILDREN)
                self._micro_cpu += (after.ru_utime - before.ru_utime) + (after.ru_stime - before.ru_stime)
            verdict = out.decode("utf-8", "replace").strip().splitlines()[-1:] if out else []
            ok = p.returncode == 0 and bool(verdict) and json.loads(verdict[0]).get("ok") is True
            cpu = (after.ru_utime - before.ru_utime) + (after.ru_stime - before.ru_stime)
            self.micro_log.append(f"{old} q={len(ids)} rc={p.returncode} ok={ok} cpu={cpu:.2f} {verdict[:1]}")
            return ok
        finally:
            shutil.rmtree(d, ignore_errors=True)

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
    for line in sel.micro_log:
        print("micro:", line, file=sys.stderr)


if __name__ == "__main__":
    main()
