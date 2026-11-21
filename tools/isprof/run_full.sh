#!/bin/sh
# usage: run_full.sh base|inst <tag>   (inside rwx-cov-local; /work and /tools mounted)
set -u
MODE=$1; TAG=$2
export SKIP_INTEGRATION=0 PYTHONDONTWRITEBYTECODE=1
if [ "$MODE" = base ]; then
  cd /work/sqlglot
  python /tools/isprof/measure.py python -m pytest -n 3 -q -p no:cacheprovider -rf > /work/isprof/full_$MODE$TAG.txt 2>&1
else
  rm -rf /work/isprof/prof_$TAG; mkdir -p /work/isprof/prof_$TAG
  cd /work/isprof/tree
  ISPROF_DIR=/work/isprof/prof_$TAG PYTHONPATH=/tools/isprof/rt python /tools/isprof/measure.py python -m pytest -n 3 -q -p no:cacheprovider -p isprof_rt -rf > /work/isprof/full_$MODE$TAG.txt 2>&1
fi
tail -n 3 /work/isprof/full_$MODE$TAG.txt
