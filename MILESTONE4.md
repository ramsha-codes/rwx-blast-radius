# Milestone 4: closing the leaderboard gap (bounded, evidence-first)

Branch `milestone-4-optimization`, created from the pushed M3 head `15f74db` (== `origin/milestone-3-research`).
`main`, `578acca` and the submitted M3 commit are untouched. Nothing pushed or submitted.

## Summary

| Candidate | Sample s | Misses | Notes |
|---|---|---|---|
| M3 (official 251.2 s) | 191.773 | 0 | baseline reproduced |
| **M4: traced subprocess test** | **185.541** | **0** | -3.2 %, sound, committed |

The only change adopted is small and provably safe: `test_lazy_load` (which runs `import sqlglot` in a
fresh interpreter) is now mapped from a real coverage trace of that interpreter, instead of "always run
on any production-code change". It is selected only when a changed line is executed during
`import sqlglot` (12 of 70 generated mutations vs. all of them before).

The leaderboard gap (172.0 vs our 251.2 official) is **not** closed by this milestone. Bigger wins exist
but none could be validated: see "What blocked validation".

## Phase 1: where the sample's 191.8 s goes (M3)

`tools/breakdown.py`: makespan 123.8 s + worker overhead 68.0 s.

* 4 commits cost ~25 s each (~100 s total): they select `TestExecutor::test_execute_tpcds` (21.5 s).
* 3 dialect/class-level commits cost 9-13 s each (~33 s): class-level lines use the file/instantiation
  fallback (hundreds of tests, including `test_generator_memory`, 6.7 s).
* ~54 s is the unavoidable 2 s floor for each commit that selects anything.
* 3 comment commits cost 0. No sample commit triggers the 80 % central-line fallback.
* On 70 generated mutations (selection only, no ground truth): avg cost 10.8 s; central fallback fires
  for 6/70 (all would already select 740-1130 tests); `test_execute_tpcds` selected in 21/70.

## Experiments

| # | Experiment | Result |
|---|---|---|
| 1 | Trace `import sqlglot` in a fresh interpreter, attribute to `test_lazy_load` (`tools/trace_subprocess.*`) | **Adopted**: 191.773 -> 185.541 s, 0 misses; 4/4 labeled mutations still 0 misses |
| 2 | *Analysis only*: drop `test_execute_tpcds` | 114.3 s but **2 sample misses** -> proves the test is load-bearing; rejected |
| 3 | *Analysis only*: drop `test_generator_memory` | 179.1 s, 0 misses, but no evidence it is safe; "never exclude because expensive"; not adopted |
| 4 | Scheduler refinement (M3) | no gain (LPT already optimal on these sets); not revisited |
| 5 | Central-line fallback | unchanged: no evidence to relax it (it fixed the m000 collection-time miss) |
| 6 | Attribute def-use narrowing of class-level lines | designed, **not implemented**: unsound without validating dynamic access (metaclass, `getattr`, dict spreads) |
| 7 | 4 new labeled mutations (m004-m007), Docker `--memory 3g --cpus 2`, RAM watchdog | **blocked** (below) |

## What blocked validation (Phase 3)

A Docker restart brought up an unrelated Dify stack (15 `docker-*` containers) that pushed free RAM to
1.9 GB, below the 3 GB floor. My watchdog stopped only my own container (`m4mut`) within seconds; no
mutation result was produced. I did not touch the unrelated containers and did not retry. Evidence is
therefore unchanged from M3: 30 sample commits + 4 labeled mutations, 0 misses. Full-suite coverage was not rerun.

## Remaining risks

* Validation is still thin (4 labeled mutations); 300 s per miss vs ~8 s savings per avoided test set.
* Over-selection remains in class-level dialect edits, which are likely common in the hidden set.
* Map built from a CRLF checkout (tests passed).
* Official practice for M3 (251.2 s) is ~1.31x the sample score; the leader's 172.0 implies roughly
  131 s sample-equivalent, i.e. ~30 % below us. Likely sources: class-level precision and `test_generator_memory`-style
  broad relations, not `test_execute_tpcds` (experiment 2 shows skipping it is unsafe).

## Is this suitable for an official submission?

Technically yes (sound, small, validated on the sample and the container), but the benefit is ~3 %
(~8 s officially at the 1.31x ratio), far from the 79 s gap. **I do not recommend spending a submission on
this alone.** Bundle it with a larger, validated precision gain.

## Recommended next steps (need >3 GB free RAM)

1. Targeted validation instead of full-suite runs: for class-level dialect mutations, run only the tests the
   *wide* rule selects (a few hundred tests, ~30 s each) and check that a narrower rule's selection covers every
   failure. That tests def-use narrowing and `test_generator_memory` relations at ~10x lower cost than full-suite labeling.
2. Resume the 70-mutation labeling (`HANDOFF.md`) with `-n 2` once memory allows.
3. Rebuild the map from an LF checkout.
