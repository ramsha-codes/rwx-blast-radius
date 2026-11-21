#!/bin/sh
# Map-build time only. Runs pytest under coverage in the *labeling image + coverage* with
# coverage started in every process (xdist workers and spawned pool children) via a .pth file.
# Usage: run_coverage2.sh <workers> [pytest args...]
set -e
N=$1; shift
cd /work/sqlglot
RAWDIR=${RAWDIR:-raw}; COVOUT=${COVOUT:-covout}
export PYTHONPATH=/work/sqlglot:/tools MAP_RAW_DIR=/work/$RAWDIR SKIP_INTEGRATION=0
export COVERAGE_PROCESS_START=/tools/covrc
rm -rf /work/$RAWDIR /work/cov /work/$COVOUT /work/sqlglot/.coverage*
mkdir -p /work/cov /work/$COVOUT
python -m pytest -p mapplugin -n "$N" -q -p no:cacheprovider "$@" 2>&1 | tail -6
unset COVERAGE_PROCESS_START
python -m coverage combine --data-file=/work/$COVOUT/.coverage /work/cov >/dev/null
ls /work/cov | wc -l
