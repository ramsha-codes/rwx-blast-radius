# Milestone 2: dependency-aware test selection

## Result (official `score.py`, 30 sample commits)

| Strategy | Simulated s | Misses | Avg tests/commit | Zero-test commits |
|---|---|---|---|---|
| Milestone 1: all tests, 4 workers | 1104.510 | 0 | 1620 | 0 |
| Direct file-level, no pool rule | 883.729 | 2 | 177.5 | 0 |
| Direct file-level + pool rule | 787.573 | 0 | 197.5 | 0 |
| Line-level hybrid, no pool rule (first M2 candidate) | 1324.250 | 4 | 37.9 | 4 |
| **Line-level hybrid + pool rule (final)** | **458.703** | **0** | **50.5** | **3** |

Final vs Milestone 1: -645.8 s (-58.5%). By kind: code 16 commits (avg 92 tests), fixture 8
(avg 1), multi 3 (avg 9), comment 3 (0 tests). CPU in the container: ~0.27 s, max RSS ~30 MB,
~1 s wall (limit 180 s). Reproduce: `python tools/evaluate.py`, `python tools/evaluate_modes.py`.
The sample set is only 30 commits, so treat 458.7 s as optimistic (see Limitations).

Not measured: "transitive static import graph" selection. `sqlglot/__init__.py` eagerly imports the
core modules and every test imports `sqlglot`, so a static closure selects essentially the full suite
for any core-file change; it adds nothing over the coverage-based map.

## How it works

`selector.py` (runtime, stdlib only) + `selector_map.json.gz` (257 KB, committed plain file).

1. Parse each unified diff into changed files and changed *old-file* lines (patches are against the
   pinned commit, so old line numbers index the map).
2. The map stores, per line of every `.py` file in `sqlglot/` and `tests/`, the set of tests to run
   if that line changes. It is built from the pinned commit only (see `tools/`):
   * per-test line coverage of sqlglot's own suite (`SKIP_INTEGRATION=0`, the labeling image);
   * a statement-aware unit (multi-line statements share coverage);
   * for class-/module-level lines (executed at import, so coverage cannot see their effect) the
     fallback is every test that ran any line of that file, plus every test that instantiated a
     Parser/Generator/Tokenizer/Dialect/Expression class defined (via MRO) in that module;
   * `def` headers/decorators use the union of the function body's coverage; docstring edits add
     `tests/test_docs.py`; `else:`/`try:` structural lines use the enclosing function;
   * insertions use the enclosing function's coverage (or file level at class/module scope);
   * fixture files map to the tests that opened them (setUpClass reads map to the whole class).
3. Comment/blank-only additions or removals select nothing unless they fall inside a multi-line string.
4. Conservative fallbacks to ALL tests: unparsable patch, binary change, a `.py` file that is not
   in the map (new/unknown module under `sqlglot/`, conftest, setup scripts), any non-inert
   non-Python file (e.g. `pyproject.toml`, `setup.cfg`). Docs/benchmarks/packaging metadata are inert.
   A new `tests/test_*.py` file selects nothing (it has no test number).
5. **Process-pool rule.** `TestOptimizer` and `TestExecutor` run work in spawned
   `ProcessPoolExecutor` children, which coverage does not attribute to the calling test. Those
   24 tests (33.4 s recorded, found by static AST analysis in `tools/build_map.py`, not by answers)
   are always added whenever a non-comment line under `sqlglot/` changes.
6. Selected tests go through the Milestone 1 LPT scheduler (1-8 workers, 2 s per worker).
   Any exception falls back to running everything; stdout stays valid JSONL (logs go to stderr).

No patch, edit category or sample answer is stored or consulted; `answers.json` is read only by
`tools/evaluate*.py` for scoring.

## Why the first candidate missed (diagnosis)

The 4 misses (and 13 missed tests) were all tests that route the work through the spawned process
pool; the mutated line was executed in a child process and was credited to unrelated tests (or
nothing). I first suspected pytest-9 subtest context resets and thread pools; a context-switch fix
changed nothing, which pointed to the process pool. This is a general gap in coverage-based maps,
not a sample quirk, so the fix is a general rule, not case patches.

## Reproducing the map (not run during the build or submission)

`tools/run_coverage.sh` inside the labeling image (`python:3.13-slim@sha256:e48f...`, clones
sqlglot at the pinned commit into `work/`, installs `requirements.lock` + coverage), with
`tools/mapplugin.py` recording fixture opens and instantiated classes, then
`python tools/build_map.py --repo work/sqlglot --cov work/sqlglot/.coverage --raw work/raw
--tests sample/tests.json --out selector_map.json.gz`. The coverage run takes ~7-12 min on 4
cores, which is why the map is committed instead of built in the 10-minute Docker build. Sources:
sqlglot's repository at the pinned commit and PyPI only. `work/`, `sample/` and `output.jsonl`
are git-ignored.

## Limitations / risks

* Line coverage says a test *executes* a line, not that a mutation of it would *fail* the test;
  we over-select (safe) but we depend on coverage being complete. Known gap: the process pool
  (handled conservatively). Other possible gaps: behavior driven by data files not opened through
  `open`, environment-dependent tests, tests whose coverage changes under mutation (a mutation that
  makes a test reach a *different* line, e.g. flipping a guard so a never-run branch executes,
  is only caught if some test covers the mutated line itself).
* 30 sample commits is a tiny validation set; there are no per-category held-out commits. A miss
  costs 300 s (about 8x a full run), so a 1-in-20 miss rate would cancel most of the gain.
* The pool rule costs ~29 s (the longest pool test is 28.8 s) on nearly every code commit; it is
  now the dominant cost.
* The map assumes the same `tests.json` ids as the sample; tests absent from the map are always
  included when anything is selected.

## Next milestone

1. Trace the pool children (coverage with `COVERAGE_PROCESS_START` + a per-task context set in the
   child) so the 24 pool tests can be selected by line instead of always, targeting the ~29 s
   floor on code commits.
2. Build a mutation-based self-check (generate our own line mutations of the pinned commit, run only
   the selected tests and a random sample of unselected ones) to estimate the true miss rate on
   unseen commits instead of relying on the 30-commit sample.
