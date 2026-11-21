# Milestone 11 submission candidate — **GO (pending owner approval)**

* Branch `m11-submission-candidate`, created from M8 `10eb5b5`.
* The only functional change: `selector_map.json.gz` is replaced by the M11 function-scope per-test fresh-process
  overlay, from `milestone-11-overlay` `15d07b9` (sha1 `a189d867…`).
* `selector.py`, Dockerfile and `isprof_profile.json.gz` are byte-identical to M8.
* M8, M9 and M10 branches are untouched. Nothing pushed, merged or submitted.
* Map commit: `9a2e004`. This report is committed on top of it; the image contents are unaffected because the
  Dockerfile copies only the selector, the map and the profile.

## Validation

| Check | Result |
|---|---|
| Map loads; test id list and order identical to M8 (1 620); every `tests.json` id mapped | PASS (`tools/m11cand/verify_map.py`) |
| Same files, fixtures, pool/proc/unmapped lists; file-level and fixture sets identical | PASS |
| Every per-line / insertion set ⊇ M8 (none lost a test; 67 876 entries widened) | PASS |
| `isprof_profile` `tests_sha` valid against the candidate map; 0 of 403 profile sites certify an overlay-added test | PASS |
| All 349 audit gap statements now select tpcds | PASS |
| Official-flags run (amd64, `--user 65534`, `--read-only`, `--network none`, `--cpus 2`, `--memory 4096m`, no swap, cap-drop ALL, no-new-privileges, pids 256) | exit 0, **135.300 s, 0 misses** |
| JSONL (`tools/check_output.py`) | 30 lines, no duplicate/missing/unknown commits, no repeated tests, workers ≤ 8, no BOM, 6 420 bytes |
| Determinism | two runs byte-identical; output byte-identical to the M8 image (sample selections are unchanged) |
| Clean `git archive 9a2e004` build (`--no-cache`) + official run | 135.300 s, 0 misses, output byte-identical to the working-tree build |
| Reproducibility | two independent no-cache builds + working-tree build: identical `/app` contents (hash `9a55c1c3…`), Python 3.13.18 (pinned base digest) |
| Container resources (3 runs) | CPU 0.13–0.17 s, peak memory ~34 MB (M8: 0.16 s, 37 MB) |
| Sizes | map 225 529 B (M8 279 372 B); image 176.7 MB; repo archive 460 800 B (M8 512 000 B) |

## Regression evidence

Production `selector.py` with the candidate map, labels used only for scoring:

| Set | M8 missed commits / tests | Candidate missed | Candidate cost vs M8 |
|---|---|---|---|
| sample (30) | 0 / 0 | 0 | 135.3 = 135.3 s |
| M11 audit reproductions (16) | 8 / 535 | **0** (535 recovered) | 504.2 vs 130.1 s |
| M11 independent full-suite set (7 labeled) | 4 / 1 915 | **0** (1 915 recovered) | 155.0 vs 99.8 s |
| general (M3), isprof ×2 (M8), clsprof ×2 (M9), M10 fresh | 0 | 0 | +3.6 % over these 290 ordinary commits |

## Residual risks (unchanged from `MILESTONE11_OVERLAY.md`, branch `milestone-11-overlay`)

* Order-dependent state from *other* tests' code paths is not covered.
* Module/class-level edits that break import outright keep M8's file-wide rule.
* Labels are partial for several corpora.
* Expected official effect: the same selections as M8 on the sample, and a small cost increase only on commits that
  edit cold-initialisation function bodies, where M8 would otherwise miss failing tests.

## Recommendation

**GO**, subject to explicit owner approval to push and submit. Fallback: M8 `10eb5b5` (official 241.2 s).
