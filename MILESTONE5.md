# Milestone 5: precision and robustness (analysis-only; no selector change adopted)

Branch `milestone-5-precision`, from M4 `cd289c3`. Nothing pushed or submitted; selector, map and
M4 score (185.541 s, 0 misses) are unchanged.

## Preflight
Branch/HEAD/tree verified clean at `cd289c3`; `docker ps` printed no containers; free RAM 3.73 GB
(above the 3 GB floor). No mutation or container jobs were run in this milestone.

## Phase A: where the cost goes (sample, `tools/breakdown.py`, `tools/ablation.py`)
| Component | Evidence |
|---|---|
| Oracle floor (only failing tests that were selected, same scheduler) | 94.4 s vs 185.5 s: precision headroom is ~91 s |
| `test_execute_tpcds` (21.5 s) in 4 commits (2haz, 2jrq, 3utz, 66ks) | ~100 s of cost. Fails on only 2 sample commits (dropping it = 2 misses, M4 exp. 2), so ~50 s is "wasted" but not separable by any static rule |
| `test_generator_memory` (6.7 s), class-level dialect edits (4d63, 535z) | dropping it: 179.1 s, 0 misses (-6.4 s, 3.5 %) |
| Fixed fallbacks (`extra_always`, `unmapped`, `proc`) | 0 tests selected on all 30 sample commits: no cost |
| Central 80 % fallback | 0 sample commits; 6/70 generated mutations (all would select 740-1130 tests anyway) |
| 2 s per-worker floor | ~66 s of 185.5 s, unavoidable |

Why the tpcds cases are not narrowable: in 2haz (`==` vs `is` on an enum), 66ks (`is None` -> `== None`)
and 3utz the changed line really is executed by tpcds; two of these are semantically equivalent
mutants. Whether a mutation is behaviour-preserving cannot be decided from coverage.

`test_generator_memory` only asserts that 1000 `dialect.generator()` calls do not grow memory. It can fail only
through per-instantiation allocation or a crash while constructing a dialect. Class-level edits in
nested `Tokenizer`/`Parser` classes are therefore very unlikely to fail it, and function-body edits it
runs are already selected by line coverage. A narrower rule (drop it for class-level lines outside
`Generator`/`Dialect`) is plausible but needs a map rebuild plus validation.

## Phase B/C: experiments
None run. No candidate had enough justification to spend mutation labeling on (budget: 4 mutations),
and a single-digit-second gain cannot be validated with 4 mutants. I did not weaken any rule.

## Findings and recommendation
* Adopted: nothing. Strongest validated implementation remains M4 (185.541 s, 0 misses).
* Best next candidate: restrict `test_generator_memory` to edits in generator/dialect-construction code
  (max gain ~6.4 s sample, ~8 s official-equivalent). Requires map rebuild (LF checkout) and
  mutation labeling of class-level lines; run only with >3 GB free RAM.
* The remaining ~75 s of tpcds cost cannot be recovered without per-mutant ground truth; the only
  evidence-based route is labeling many mutants and learning which line regions tpcds never fails on.
* A new official submission is **not worthwhile** from this milestone (no code change).

## Reproduce
`python tools/breakdown.py`, `python tools/ablation.py`, `python tools/mutation_costs.py`.
