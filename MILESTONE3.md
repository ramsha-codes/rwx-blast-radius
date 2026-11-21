# Milestone 3: precise process-pool coverage + mutation validation

Branch `milestone-3-research` (main / `578acca` untouched).

## 1. Executive summary

* Milestone 2's biggest cost was a blanket "always run the 24 process-pool tests" rule: it made
  every code commit cost >= ~25 s (`TestExecutor::test_execute_tpcds` alone is 21.5 s).
* Coverage can see pool children if coverage is started in every child (`.pth` +
  `COVERAGE_PROCESS_START`) **and** each task switches its coverage context to the submitting test.
  Expression pickling (`serde.dump/load`) also has to be exercised inside that context.
* With that map the sample drops **458.703 s -> 191.773 s, 0 misses** (-58%). Official practice
  for Milestone 2 was 621.7 s vs 458.7 s locally, so expect the hidden set to cost more than the sample.
* Mutation validation could only be partly completed: 4 of 70 planned runs finished before the OS
  memory-pressure guard stopped the job (I did not restart it). Treat the robustness evidence as
  **thin**. 0 of 4 missed after the "central line" rule; 1 of 4 missed before it.
* Recommendation: do **not** replace the submitted main yet. Finish the mutation run (command in
  HANDOFF.md) or use an official practice submission of this branch as held-out evidence.

## 2. Technical discoveries

1. **Process pools hide code from coverage.** `TestOptimizer` (class-level spawn pool) and
   `TestExecutor` (pool per test) run optimizer/executor code in children; coverage attributed those
   lines to unrelated tests (the child's context was whichever test created the pool).
2. **Cross-process pickling is an invisible dependency.** `Expr.__reduce__` uses `serde.dump/load`,
   run by the pool's feeder/reader threads outside any test context. A `serde.py` change failed 13
   `TestOptimizer` tests that the map missed until tasks round-tripped args/result inside the context.
3. **`test_execute_tpch` children execute no sqlglot code** (`mp_execute` returns `None` unless a
   fixture is flagged `execute`), so it needs no special handling.
4. **Collection-time execution.** Test modules run SQL parsing at import; a broken central line fails
   whole *files* at collection, which no per-test context captures (and lazy caches make the first
   collected module absorb the lines).
5. **Subprocess tests** (`TestDialect::test_lazy_load`, 0.37 s) start a fresh interpreter: invisible to
   coverage; depends on the whole `import sqlglot` chain.
6. The local sqlglot checkout has CRLF endings (Windows git); line numbers are unaffected, but the
   map should ideally be rebuilt from an LF checkout (see weaknesses).

## 3. Experiments (experiment log)

| # | Candidate | Sample s | Misses | Avg tests | Notes |
|---|---|---|---|---|---|
| 0 | M2 (verified, main `578acca`): line map + pool rule | 458.703 | 0 | 50.5 | official practice 621.7 |
| 1 | Child-process coverage via `.pth` + submit wrapper, small bounded run | - | - | - | optimizer children attributed correctly; tpch children do nothing |
| 2 | Full run #1 with child tracing, pool rule OFF | 485.357 | 1 (3utz) | 38.5 | 185.4 s + one 300 s miss: serde gap |
| 3 | + arg/result pickle round-trip inside task context (24 pool tests re-traced, merged) | **185.357** | 0 | 39.0 | |
| 4 | Scheduler hill-climb after LPT | 185.357 | 0 | - | no gain, rejected (LPT already optimal here) |
| 5 | + subprocess-test rule (`test_lazy_load`) | 191.773 | 0 | 40.0 | +6.4 s total, closes the fresh-interpreter gap |
| 6 | Full run #2: + per-module collection contexts | 191.773 | 0 | 40.0 | collect contexts cannot attribute lazily cached imports; kept |
| 7 | + central-line fallback (>=80% of suite => run all) | **191.773** | 0 | 40.0 | fixes collection-time hole (m000), no sample cost |
| 8 | M3 map with pool rule ON (conservative variant, `POOL_RULE=True`) | 458.887 | 0 | 51.6 | safe fallback if validation shows pool misses |

Coverage runs: 2 full (12 and 10 min) + 2 small (3 min and a 10 s failed one), within the 3-run budget.
Resource: container CPU 0.22 s, max RSS 31.5 MB, ~1 s wall; map 264 KB.

## 4. What worked / 5. What failed

Worked: child tracing with task contexts; pickle round-trip; central fallback; subprocess rule;
statically discovered always-run lists (no answers involved).
Failed / rejected: pytest-cov contexts (subtests reset them); thread-pool theory (it is a process pool);
scheduler hill-climbing (no gain); `git`-based mutation harness (no git in slim image); first harness
copy missed `sqlglotc/`, causing 3 spurious `test_sqlglotc` errors (fixed).

## 6. Benchmark comparison

| Variant | Simulated s | Misses |
|---|---|---|
| M1 all tests | 1104.510 | 0 |
| M2 | 458.703 | 0 |
| **M3 candidate (this branch)** | **191.773** | **0** |
| M3 with pool rule | 458.887 | 0 |

## 7. Mutation robustness

Framework: `tools/mutate.py` (70 seeded patches: operator/constant flips, inserted/deleted statements,
comment-only, fixtures, multi-file), `tools/run_mutations.sh` (full-suite run on a throw-away copy;
`tools/failrec.py` records failing tests and collection errors), `tools/mutation_eval.py`.
Nothing from it feeds the selector. **Completed: 4 of 70.**

| Mutation | Real failures | Selected (final) | Result |
|---|---|---|---|
| m000 core tokenizer flip | 1525 | all | miss before central rule, hit after |
| m001 comment | 0 | 0 | ok |
| m002 optimizer | 0 | 1 | ok |
| m003 hive generator | 2 | 3 | ok |

0 missed commits of 4 evaluated; statistically meaningless. The job was stopped at 11 minutes by the
OS memory guard (1.4 GB free) and I stopped its container; no restart was attempted.

## 8. Remaining weaknesses

* **Validation is thin** (4 mutations, 30 sample commits). A miss costs 300 s (~8 full runs).
* Line coverage says "executed", not "would fail"; mutations that make a test reach a *different*
  line are only caught if some test covers the mutated line.
* Collection-time and lazy-import attribution is approximate (central rule mitigates).
* Map built from a CRLF checkout (tests passed; rebuild from LF to match the labeling environment).
* Sample/practice gap: 458.7 local vs 621.7 official suggests the hidden commits touch more central code.
* The 30-sample score is not an estimate of the final score.

## 9. Recommended final algorithm

M3 candidate as committed (`POOL_RULE=False`, subprocess rule on, central-fallback 0.8, map from
`tools/`), **provided** a larger mutation run (>= 40 completed, 0 misses) or an official practice
submission shows no misses. If any pool-test miss appears, set `POOL_RULE = True` (458.9 s) rather than
guessing; if other misses appear, lower `CENTRAL_FRACTION`.

## 10. Next actions before the deadline

1. When memory is free, run the mutation job (HANDOFF.md) with `-n 2`; review misses for *general* causes.
2. Submit this branch as an official **practice** submission (user decision) for held-out evidence.
3. Rebuild the map from an LF checkout; re-verify the sample.
4. If time: trace subtest-heavy collection per module more precisely, add dialect-aware fallbacks.
