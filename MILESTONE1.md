# Milestone 1: duration-aware worker scheduling

Test selection is unchanged (all 1,620 tests per commit, no skipping). Only the worker split changed.

## Method
- `selector.py` tries 1..8 workers. For each count it builds a Longest-Processing-Time split
  (integer ms, scorer rounding, deterministic tie-breaks) and keeps the count minimising
  `busiest load + 2 s x workers`. No sample answers or patch contents are consulted.

## Results (sample, local scorer)
| workers | busiest (s) | cost/commit (s) |
|---|---|---|
| 1 | 103.047 | 105.047 |
| 2 | 51.524 | 55.524 |
| 3 (baseline) | 34.349 | 40.349 |
| **4** | **28.817** | **36.817** |
| 5-8 | 28.817 | 38.8-44.8 |

The single 28.817 s test is a floor on the busiest worker, so 4 workers is optimal for
the full test set. Score: 1210.470 -> 1104.510 s (-8.75%), 0 misses.
Container run: ~2 s wall, ~0.43 s CPU (user+sys).

## Limitations
- Still runs every test: the floor is ~36.8 s/commit; big gains need skipping tests.
- Durations are the recorded ones; real runtimes are not involved (simulated scoring).

## Next milestone
Safe test selection from maps built at the pinned commit (import graph / coverage per test
file, built in the Dockerfile), mapping patch-touched files to affected tests, with a
conservative fallback to the full set for risky patches (conftest, setup, non-Python),
tuned against the 300 s miss penalty. Then re-run the worker scheduler on the selected set.
