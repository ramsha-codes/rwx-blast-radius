# M19: production feasibility of the tpcds micro-check — **conditional GO (practice experiment only)**

* Branch `m19-micro`, created from M11 `28c8cfb`. Candidate code commit: `6cb0947`.
* M8, M11, M15 and M18 are unchanged. Nothing pushed, merged or submitted. The final entry stays M11.

## What changed versus M11

* **`selector.py`:** only when M11 selects `test_execute_tpcds` *and* the patch qualifies does it run a check; it
  drops tpcds only on an all-identical result.
  * Qualifying patch: one modified `sqlglot/*.py` file; every changed line inside a function body; removed lines
    match the pinned source; no changed line in the shared/import/first-touch set G; reached by 1–20 TPC-DS queries.
  * The check runs those queries on the patched code in a child process.
* **`micro_check.py`** (the child): repeats the test's per-query pipeline — `parse_one`, pickle round trip,
  `find_tables`, `execute`, `transpile(→duckdb)` — and stops at the first difference.
* **`tpcds_micro_profile.json.gz`:** 35 KB, built from the pristine pinned commit (M18 profile).
* **`pristine/`:** pinned sqlglot sources, `tests/helpers.py` and the TPC-DS fixtures, 7.0 MB, byte-identical to
  `eb11aec`.
* **Dockerfile:** copies these files and compiles their bytecode at build time. No network.

**Resource limits per check:**
* `RLIMIT_CPU` 10 s, `RLIMIT_AS` 2 GB, 20 s wall timeout;
* a new session per check, with the process group SIGKILLed after every check;
* a `/tmp` symlink tree (only the patched file is real), removed afterwards;
* a 60 s CPU cap across all checks in one batch.

**Fallback to the exact M11 selection on:** a missing or invalid profile or files, an ineligible patch, a
timeout, a CPU or memory limit, a crash, a non-zero exit, an unparsable verdict, any difference, or the batch cap.

## Phase 1: validation integrity

* **Re-checked with the real pooled tpcds test** (`--timeout=800`, JUnit and failrec): all 14 earlier
  certifications pass a second, independent time, 57/57 subtests, no timeouts. They are h018, f022, f023, m023,
  m044, m047, m060, n03, q01, q03, q05, q06 (152 s, slow but passing), q09 and q12.
* **n03's failing full-suite label** is an artefact of the old harness (`-n 3 --timeout=60`, where tpcds can time
  out). Certification evidence now uses only the real pooled test, run alone, with timeouts recorded separately.

## Phase 2: resource limits (official flags)

| Patch | Result | Selection |
|---|---|---|
| q06 (117 s CPU pathology) | killed by `RLIMIT_CPU` at 10.11 s (SIGXCPU) | tpcds kept |
| infinite-loop patch | killed at 10.11 s | kept |
| 6 GB allocation | refused by `RLIMIT_AS`, exception, counts as a difference (1.4 s) | kept |

No `/tmp` trees left behind. The hostile batch took 23 s of wall time.

## Phase 3: what a certification proves, and what is rejected

**Certification proves:** for each TPC-DS query that executes a changed line in the warm per-query profile, the
patched code yields the same duckdb SQL string, the same executor result hash and the same exception status as the
pristine code. With assumptions A1–A4, the 57 subtests' comparisons are unchanged, so the test passes as on
pristine code.
* **A1 Query independence:** no cross-query state. G removes first-touch lines.
* **A2 Profile completeness:** warm traces after a full warm-up pass.
* **A3 Only executed lines matter:** class/module-level, decorator/signature and G edits are rejected.
* **A4 Determinism:** `PYTHONHASHSEED=0` matches the profile; fingerprints were stable across passes.

**Rejected (fallback):**
* import-time and class/module-level edits;
* shared setup and first-touch lines (G);
* lines reached by more than 20 queries, or not reached by any query;
* multi-file patches and added, deleted or renamed files;
* patches not matching the pinned source;
* any resource limit or crash.

**M11's import-time fixes are untouched:** none of the 16 M11 audit patches is eligible; their selections are
identical to M11's.

## Phase 4: production economics (clean `git archive 6cb0947`, no-cache build, official flags)

* **Sample:** 135.300 s, 0 misses.
  * The output is **byte-identical to M11** (no sample commit is eligible) and deterministic over two runs.
  * CPU (all processes) 0.25 s; peak memory ~40 MB.
* **83-commit validation batch** (sample + 11 labeled eligible + 16 holdout + 16 M11 audit + 8 independent +
  2 hostile):
  * M11 1 571.2 s → M19 1 344.5 s simulated (−226.7 s);
  * check CPU 104.4 s across 31 checks, max 10.1 s each;
  * **net +122.3 s**;
  * 14 certifications, **all verified passing with the real test; 0 missed failing tests**.
* **Same batch at production defaults** (60 s batch cap): 70.3 s wall, 69.0 s CPU for all processes. That's within
  the 3 min practice and 4.5 min final limits.
* **Reproducibility and size:** two independent no-cache builds have identical `/app` contents. Repository archive
  7.6 MB (< 20 MB). Image 196 MB.

## Risks and expected official effect

* **The batch is enriched.** 27 of 83 commits are eligible; in ordinary workloads ~5–8 % of commits are.
  Realistic expectation: **≈ +5–10 s per 30 commits**, 0 on sample-like batches.
* **Worst case:** at most ~60 s of extra CPU per run, if every check is spent on failing patches.
* **Assumptions A1–A4 are empirical.** 0 false certifications across 29 eligible verified patches.

## Recommendation

**Conditional GO** for one practice-board submission of this candidate, to measure the effect on the hidden
workload. Keep **M11 `28c8cfb`** as the final unless M19 scores below 263.3 s with 0 misses.

Push and submit only with explicit approval.
