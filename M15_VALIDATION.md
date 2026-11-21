# M15: M11 + class-granular `arg_types` narrowing — validation report

* Branch `m15-m11-m9`, created from M11 `28c8cfb`. Image-input commit: `cb28748`.
* M8, M11 and the research branches are unchanged. Nothing pushed, merged or submitted.
* Change versus M11:
  * `selector.py` +91 lines;
  * `clsprof_profile.json.gz` (12.9 KB, M9's builder re-run on the **M11** map with M9's original runs t1–t3);
  * Dockerfile copies the new profile.
* The map and the isprof profile are unchanged.

## Mechanism

M11's selection is narrowed to M9's per-site dependency set **only when all of these hold**:
* every changed line of the file is a literal `"key": True|False|None|int|simple-string` entry, or a one-line literal
  `arg_types = {...}`;
* the edit sits inside **one** profiled, non-null `arg_types` statement under `sqlglot/expressions/`;
* there are no insertions-only blocks, no spreads, calls, names, lambdas or tuples, and no multi-region edits.

The dependency set comes from M9 and is null (never narrow) for:
* classes instantiated outside a test call;
* `arg_types` read by a module-level derived constant (e.g. `UNMERGABLE_ARGS`);
* spread readers (e.g. `Cast`);
* unresolved references.

`test_generator_memory` is never narrowed away (stability rule, below). The result is always ⊆ M11.

**Fail-closed loader.** Missing, corrupt, wrong-version, stale (`tests_sha`), bad-hex, bad-path or invalid-JSON
profiles all fall back to the exact M11 selection (tested). Call, name, spread, lambda and tuple values fall back.

## Phase 1: compatibility gate (passed before integration)

* **0 of 1 817** M9 site lines have M11 line/insertion sets different from M8's, so narrowing never touches an M11
  cold-start overlay credit.
* The profile rebuilt on the M11 map has dependency sets **identical** to M9's `profile4` (0 grew, 0 shrank, 0 null
  changes).
* **203 labeled patches:** no known failing test excluded; all M11-recovered failing tests (2 450 distinct across the
  repro and independent sets) remain selected. No M11 audit or independent case is narrowed.
* **Import-time and global readers reviewed** (`__init_subclass__` `required_args`, `**Cast.arg_types`,
  `UNMERGABLE_ARGS`): covered by instantiation dependency sets or null.

## Phase 3: results versus M11

| Corpus | n | Narrowed | M11 → M15 simulated | Misses |
|---|---|---|---|---|
| sample | 30 | 1 (ktz3 334 → 23 tests) | 135.3 → 130.7 | 0 |
| M11 audit repro / independent (full labels) | 16 / 7 | 0 | unchanged | 0 |
| M3 general | 70 | 3 | 792.5 → 777.1 | 0 (excluded tests executed) |
| M9 held-out ×2 | 80 | 71 | 1 589.0 → 1 303.9 | 0 (earlier excluded-test runs cover the exclusions) |
| isprof ×2, M10 fresh | 120 | 0 | unchanged | 0 |
| **Total** | 323 | | **4 924.6 → 4 619.5 (−305.1 s, −6.2 %)** | **0** |

**Excluded tests executed on mutated code** (this session): 3 M3 mutants (174 + 1 577 + 305) and 10 new adversarial
literal mutants (seed 20261125: entry deletions, flag flips on `Func` subclasses, key renames, swapped entry order;
1 593 tests).
* **All pass, with one exception:** in m051's first batch, `test_generator_memory` failed its 1 024-byte tracemalloc
  threshold (2 330 bytes, athena subtest).
* **It did not reproduce:**
  * it passed alone on the patched tree twice and on the pristine tree;
  * the identical 1 577-test batch passed on both trees.
* Three `test_sqlglotc` errors were a harness artefact: `sqlglotc/` wasn't copied. They pass with it.
* **Response:** a general stability rule (never narrow away that state-sensitive test). With it, every current
  exclusion is covered by an executed, passing run.

## Phase 4: official-style run (`git archive cb28748`, `--no-cache` build, nobody, read-only, no network, 2 CPUs, 4 GB)

* **Score:** 130.665 s simulated, 0 misses.
* **Output:** JSONL valid (30 lines, ≤ 8 workers, no BOM); two runs byte-identical.
* **Resources:** container CPU 0.33–0.42 s (M11 ~0.15 s), peak memory ~35 MB.
* **Sizes:** image 176.8 MB; repo archive 512 000 B.

## Remaining risks

* Narrowing rests on M9's warm class-instantiation traces. Instances created lazily once per process and reused by
  a later test are invisible to them. M9 mitigates this with null sets for globally instantiated classes, unstable
  tests and a structural pool guard; no counterexample was found.
* Possible reflective uses of class dicts beyond `arg_types` readers aren't modelled.
* Other state-sensitive tests (like the memory test) may exist.
* The benefit is concentrated on class-level `arg_types` edits: −4.6 s on the sample (net −4.4 s after CPU), large
  only on workloads with such edits.

## Recommendation

* **GO for one practice-board submission** as a controlled experiment. It is the only way to learn whether the hidden
  workload contains `arg_types` edits.
* **Keep M11 `28c8cfb` as the final** unless M15's practice score beats 263.3 s with 0 misses.

Push and submit only with explicit approval.
