#!/bin/sh
# Validation only. For each mutation id, apply its patch to a throw-away COPY of the pinned
# checkout and run the FULL suite to learn which tests really fail.
# Usage: run_mutations.sh <xdist workers> <id> [<id> ...]   (patches in /work/mutations)
N=$1; shift
mkdir -p /work/mutres
for id in "$@"; do
  [ -f "/work/mutres/$id.json" ] && continue
  rm -rf /tmp/m && mkdir /tmp/m && cp -r /work/sqlglot/sqlglot /work/sqlglot/tests /work/sqlglot/sqlglotc /work/sqlglot/pyproject.toml /work/sqlglot/setup.py /work/sqlglot/setup.cfg /work/sqlglot/README.md /tmp/m/
  find /tmp/m -name __pycache__ -prune -exec rm -rf {} +
  cd /tmp/m
  python /tools/apply_patch.py "/work/mutations/$id.patch" /tmp/m || { echo "$id apply-failed"; continue; }
  export PYTHONPATH=/tmp/m:/tools SKIP_INTEGRATION=0 FAIL_OUT="/work/mutres/$id.json"
  timeout 600 python -m pytest -p failrec -n "$N" -q -p no:cacheprovider --timeout=60 tests >/tmp/m.log 2>&1
  echo "$id exit=$? $(tail -1 /tmp/m.log | cut -c1-100)"
done
