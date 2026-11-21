# HANDOFF (Milestone 3)

* Branch: `milestone-3-research` (created from `578acca`). `main` and `origin/main` untouched; nothing pushed.
* Best verified local score: **191.773 s, 0 missed commits** (Docker, official flags, as `nobody`,
  one JSON line per commit, 0.22 s CPU, 31.5 MB RSS). Milestone 2 (main): 458.703 s local, 621.7 s official practice.
* Validation done: sample scorer in container; output format check (`tools/check_output.py`); 4/70
  mutations evaluated (0 misses). **Not done:** the other 66 mutations (stopped by OS memory guard).
* Active processes: none of mine. Before finishing I stopped my own coverage/mutation containers
  (`docker ps` shows only unrelated Supabase containers). Local image tags created: `rwx-cov-local`
  (pip deps + coverage, for map building), `blast-m3`, `blast-verify`, `blast-radius-entry`.
* New official submission recommended? **Not yet.** Use this branch as a *practice* submission only
  if you want held-out evidence, or finish the mutation run first. Keep `578acca` as the fallback.

## Reproduce

```sh
# sample score of the candidate (no Docker)
python tools/evaluate.py                    # selection + official score.py on sample/
python tools/evaluate_modes.py              # file-level / hybrid comparisons

# official-style container run
S="$(pwd -W)/sample"
docker build --platform linux/amd64 -t blast-m3 .
docker run --rm --platform linux/amd64 --network none --cpus 2 --memory 4096m --memory-swap 4096m \
  --pids-limit 256 --read-only --tmpfs /tmp:rw,size=64m,mode=1777 --cap-drop ALL \
  --security-opt no-new-privileges --user 65534:65534 --env HOME=/tmp \
  --volume "$S/commits:/data/commits:ro" --volume "$S/tests.json:/data/tests.json:ro" blast-m3 > out.jsonl
python score.py sample sample/answers.json out.jsonl && python tools/check_output.py out.jsonl sample/commits

# rebuild the map (needs work/sqlglot = pinned checkout; heavy: ~10-12 min, ~2-3 GB RAM)
git clone https://github.com/tobymao/sqlglot.git work/sqlglot && git -C work/sqlglot checkout eb11aec4be8cb2122afe713a4816662c3f0fb2fa
mkdir -p work/covimg && cp tools/covimg.Dockerfile work/covimg/Dockerfile && cp requirements.lock work/covimg/
docker build -q -t rwx-cov-local work/covimg
docker run --rm -v "$PWD/work:/work" -v "$PWD/tools:/tools:ro" -e RAWDIR=raw_full2 -e COVOUT=covout_full2 \
  rwx-cov-local sh /tools/run_coverage2.sh 3 tests
python tools/build_map.py --repo work/sqlglot --cov work/covout_full2/.coverage --raw work/raw_full2 \
  --tests sample/tests.json --out selector_map.json.gz

# mutation validation (heavy; run only with >3 GB free RAM; resumable; ~1-2 min per mutation)
python tools/mutate.py --repo work/sqlglot --out work/mutations --n 70 --seed 7
docker run --rm -v "$PWD/work:/work" -v "$PWD/tools:/tools:ro" rwx-cov-local sh /tools/run_mutations.sh 2 $(ls work/mutations/*.patch | sed 's#.*/##;s#\.patch##')
python tools/mutation_eval.py --no-pool-rule -v
```

`work/` and `sample/` are git-ignored; `work/mutres_harness_v1_discard` holds discarded results from
the flawed first harness (kept, not deleted).

## Milestone 4 addendum (branch `milestone-4-optimization`)

* Based on `15f74db`. Best local score **185.541 s, 0 misses** (M3: 191.773). Change: `test_lazy_load` is
  mapped from a traced `import sqlglot` run instead of an always-run rule. See `MILESTONE4.md`.
* Validation done: sample scorer, Docker official-flag run as `nobody`, clean `git archive` rebuild,
  4 labeled mutations (0 misses). New mutation labeling was blocked by low RAM (unrelated Dify containers);
  no processes of mine remain.
* Rebuild the map with the subprocess trace:
  `python tools/trace_subprocess.py work/sqlglot work/sub_code`, then
  `docker run --rm --memory 2g -v "$PWD/work:/work" -v "$PWD/tools:/tools:ro" rwx-cov-local sh /tools/trace_subprocess.sh`, then
  `python tools/build_map.py ... --sub-index work/sub_code/index.json --sub-cov work/covout_sub --out selector_map.json.gz`
  (same other arguments as in the M3 section above).
* Diagnostics: `python tools/breakdown.py` (per-commit cost), `python tools/mutation_costs.py` (selection stats on all generated mutations).
* New official submission recommended? **No** for this change alone (about 3 % gain).
