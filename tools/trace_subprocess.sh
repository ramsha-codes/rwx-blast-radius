#!/bin/sh
# Map-build time (cheap: a few seconds). Traces each extracted subprocess snippet with coverage.
# Run inside the rwx-cov-local image with /work and /tools mounted.
set -e
cd /work/sqlglot
export PYTHONPATH=/work/sqlglot
for f in /work/sub_code/[0-9]*.py; do
  n=$(basename "$f" .py)
  mkdir -p /work/covout_sub/$n
  python -m coverage run --data-file=/work/covout_sub/$n/.coverage --source=sqlglot "$f" >/dev/null
done
ls /work/covout_sub
