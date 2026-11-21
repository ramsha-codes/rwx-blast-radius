#!/bin/sh
# Prototype: baseline vs instrumented full-suite run inside the Python 3.13 labeling image (needs rwx-cov-local).
# Usage: run_profile.sh <workers> <tag>      (writes /work/isprof/prof_<tag>/*.json and log_<tag>.txt)
set -u
N=$1; TAG=$2
export SKIP_INTEGRATION=0 PYTHONDONTWRITEBYTECODE=1
unset COVERAGE_PROCESS_START
cd /work/sqlglot
echo "== baseline (pristine) =="
( time -p python -m pytest -n "$N" -q -p no:cacheprovider -rf 2>&1 | tail -n 15 ) > /work/isprof/log_base_$TAG.txt 2>&1
cat /work/isprof/log_base_$TAG.txt | tail -8
echo "== instrumented =="
rm -rf /work/isprof/prof_$TAG; mkdir -p /work/isprof/prof_$TAG
cd /work/isprof/tree
export ISPROF_DIR=/work/isprof/prof_$TAG PYTHONPATH=/tools/isprof/rt
( time -p python -m pytest -n "$N" -q -p no:cacheprovider -p isprof_rt -rf 2>&1 | tail -n 15 ) > /work/isprof/log_inst_$TAG.txt 2>&1
tail -8 /work/isprof/log_inst_$TAG.txt
ls /work/isprof/prof_$TAG | wc -l
