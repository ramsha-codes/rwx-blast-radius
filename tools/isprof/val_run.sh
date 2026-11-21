#!/bin/sh
# Validation: for each held-out mutant, run ONLY the tests the predictor excluded, on a patched COPY of the
# pinned checkout, and record failures. usage: val_run.sh <workers> <id>...   (ids in /work/isprof/val/<id>.ids,
# patches in /work/isprof/heldout/<id>.patch; results /work/isprof/valres/<id>.json)
N=$1; shift
mkdir -p /work/isprof/valres
for id in "$@"; do
  rm -rf /tmp/m && mkdir /tmp/m && cp -r /work/sqlglot/sqlglot /work/sqlglot/tests /work/sqlglot/sqlglotc /work/sqlglot/pyproject.toml /work/sqlglot/setup.py /work/sqlglot/setup.cfg /work/sqlglot/README.md /tmp/m/
  find /tmp/m -name __pycache__ -prune -exec rm -rf {} +
  cd /tmp/m
  python /tools/apply_patch.py "/work/isprof/heldout/$id.patch" /tmp/m || { echo "$id apply-failed"; continue; }
  export PYTHONPATH=/tmp/m:/tools:/tools/isprof SKIP_INTEGRATION=0 FAIL_OUT="/work/isprof/valres/$id.json" ISPROF_IDS="/work/isprof/val/$id.ids"
  timeout 900 python -m pytest -p failrec -p idfilter -n "$N" -q -p no:cacheprovider --timeout=120 tests >/tmp/v.log 2>&1
  echo "$id exit=$? $(tail -1 /tmp/v.log | cut -c1-110)"
done
