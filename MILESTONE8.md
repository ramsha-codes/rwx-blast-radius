# Milestone 8: operand-observation profile for identity/equality swaps

Branch `milestone-8-isprof` (from M7 `d6a38b9`, unchanged). Nothing pushed or submitted.
Local sample score: **135.300 s, 0 misses** (M7/M5: 185.541 s). Official-style Docker run as `nobody`: same.

## What it is
`isprof_profile.json.gz` (15.8 KB) is a **baseline execution artifact of the pinned commit**, like the coverage map:
for every `a is b` / `a is not b` site inside a function body (679 of 682 sites) and every test, whether all operand
pairs observed there were of a type with builtin equality **and** identity agreed with equality (`is` == `==`).
It contains no failing-test information and no patch information. Nothing in it or in the selector refers to the
sample patches or their answers.

Use: if a patch changes a single line that is exactly one `is`->`==` (or `is not`->`!=`) token swap at a profiled
site, tests whose observations show the swap is unobservable are not selected; coverage still decides everything
else. Every other edit shape is handled exactly as in M7.

## Safety design (all fail closed)
* Operand types: `==` is evaluated only if both types have `__eq__/__ne__` from `object/str/int/float/bytes` (so no
  user code ever runs); any other type records "unsupported" and the pair is never certified.
* Attribution: only a test's *call* phase counts. Import/collection/fixtures/`setUpClass`/untagged subprocesses are
  "unattributed": a site seen unattributed as infected/unsupported is disqualified for every test. Module- and
  class-level sites are not instrumented. Spawned `ProcessPoolExecutor` children are tagged with the submitting test.
* Determinism: the profile is the intersection of **two independent full-suite runs**; any (test, site) whose
  observation differs between runs is not certified.
* Selector: profile missing/corrupt/wrong version/stale (sha1 of the map's test order) => coverage only. Only
  single-line, single-token swaps with exactly one `is` on the line, in a `modified` `sqlglot/` file, whose every
  block is such a swap, are narrowed. A test is dropped only if it covers the line AND is certified for the site.
  Tests not covered by the line, or covered but with no certification (no observation, unsupported type, import-time,
  nondeterministic), stay selected. Selection never grows relative to M7.

## Validation
| Check | Result |
|---|---|
| Full suite, pristine vs instrumented (Py 3.13 image, 4 CPUs, -n 3) | identical: 1620 passed, 1 skipped, 25 440 subtests (3 runs) |
| Instrumentation cost | full suite CPU 415.5 s -> 423.7 s (+2 %, run noise ~30 %; 2nd instrumented run 360.9 s); `test_execute_tpcds` alone (worst case) +25..32 % wall; max process RSS 1.80 -> 1.88 GB (+4 %) |
| Sites profiled | 660/679 executed (97.2 %); 403 certified for >=1 test; 43.5 % of covered (test, site) pairs certified; 74 sites seen unattributed, 36 disqualified; 14 never covered |
| Held-out set 1 (seed 20261121, 40 mutants) | 25 had exclusions: 3 038 excluded tests executed on the mutated code, **0 failures** |
| Held-out set 2 (seed 424242, 40 new mutants, 25 `is`/15 `is not`, no site shared with set 1) | 25 had exclusions: 2 796 excluded tests executed, **0 failures**, counts match |
| Fallback checks `tools/isprof/check_fallback.py` | 180 patches x (profile off + 9 bad-profile variants) identical to M7; enabled selection never wider than M7 and differs on exactly the 52 pure swaps; 219 non-narrowable shapes identical to M7 |
| Unit tests | `tools/test_isprof_selection.py` (6), `tools/test_sqlglotc_selection.py` (5): pass |
| Docker (official flags, `nobody`, read-only, no network) | simulated 135.300 s, 0 misses, `check_output` OK, 6 empty commits |
| Selector process | ~0.2 s CPU (M4 ~0.1 s), 37 MB RSS (M4 33 MB) |

Held-out mutations are single `is`->`==`/`is not`->`!=` swaps chosen uniformly at random from the instrumented
sites (the 2 sample-edit lines excluded from set 1; set 2 excludes set 1's sites). Pooled: coverage-only 1 094.0 s ->
601.9 s (-45 %, 6.2 s per mutant). 0 false negatives in 50 validated mutants / 5 834 executed excluded tests
(95 % upper bounds: ~6 % per mutant, ~0.05 % per test).

## Limits and risks
* Gain exists only for commits that are pure identity/equality swaps (2 of the 30 sample commits; 95 % interval
  2-21 %). Expected ~6 s per such commit => roughly 12 s (range 4-39 s) per 30 commits out of sample; the 50.2 s on the
  sample is in-sample (both sample cases sit on the 21 s TPC-DS path).
* Certification is observational on one environment (the labeling image) with two agreeing runs; a behaviour that
  only appears under other timing/hash seeds is not excluded. A wrong exclusion costs 300 s.
* The profile is keyed by (file, line, operator) of the pinned commit; it is valid only for that commit and the test
  order of the map (sha-checked).
* Rule interpretation: the artifact is derived purely from executing the pinned commit; it is not a table from
  patches or edit kinds to failing tests. The selector's recognition of a swap is a general diff rule. Still, it is
  the one place that sits near the "no table from a kind of edit" wording: confirm with organisers if in doubt.
  `isprof_profile.json.gz` can be deleted to revert to exact M7 behaviour.

## Reproduce
```sh
python tools/isprof/transform.py work/sqlglot/sqlglot work/isprof/pkg/sqlglot work/isprof/sites.json
# copy work/sqlglot to work/isprof/tree and replace its sqlglot/ with work/isprof/pkg/sqlglot, then twice:
docker run --rm --memory 3500m --cpus 4 -v "$PWD/work:/work" -v "$PWD/tools:/tools:ro" rwx-cov-local sh /tools/isprof/run_full.sh inst 1   # and 2
python tools/isprof/merge.py --sites work/isprof/sites.json --map selector_map.json.gz --out isprof_profile.json.gz work/isprof/prof_1 work/isprof/prof_2
python tools/isprof/heldout.py --repo work/sqlglot --sites work/isprof/sites.json --out work/isprof/heldout2 --exclude-dir work/isprof/heldout --n 40 --seed 424242
python tools/isprof/run_predict.py --profile isprof_profile.json.gz --patches work/isprof/heldout2 --tests sample/tests.json --out work/isprof/pred_heldout2.json
docker run ... sh /tools/isprof/val_run2.sh 3 $(cat work/isprof/val2_order.txt)     # validation of the exclusions
python tools/isprof/check_fallback.py; python tools/test_isprof_selection.py; python tools/evaluate.py
```
