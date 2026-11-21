#!/bin/sh
# usage: run_excl.sh <pid> <patch>   runs the tests M15 excludes (vs M11) on the PATCHED tree
pid=$1; P=$2; W=/tmp/x_$pid; OUT=/work/m15/res/$pid; mkdir -p $OUT; rm -rf $W; mkdir $W
cp -r /work/sqlglot/sqlglot /work/sqlglot/tests /work/sqlglot/pyproject.toml /work/sqlglot/setup.py /work/sqlglot/setup.cfg $W/
find $W -name __pycache__ -prune -exec rm -rf {} +
python /tools/apply_patch.py "$P" $W >/dev/null || { echo "$pid apply-failed"; exit 0; }
cd $W
PYTHONPATH=$W:/tools SKIP_INTEGRATION=0 FAIL_OUT=$OUT/fail.json PYTHONDONTWRITEBYTECODE=1 timeout 900 python -m pytest -p failrec -q -p no:cacheprovider --timeout=300 -n 2 --junitxml=$OUT/junit.xml @/work/m15/ids_$pid.txt > $OUT/log 2>&1
echo "$pid exit=$? $(tail -1 $OUT/log | cut -c1-90)"
rm -rf $W
