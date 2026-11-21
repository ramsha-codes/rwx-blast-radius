#!/bin/sh
# Runs inside python:3.13-slim (the labeling image). Map-build time only.
set -e
cd /work/sqlglot
pip install -q --no-cache-dir -r /req.lock coverage pytest-cov >/dev/null 2>&1
export PYTHONPATH=/work/sqlglot:/tools MAP_RAW_DIR=/work/raw SKIP_INTEGRATION=0
rm -rf /work/raw .coverage*
python -m pytest -p mapplugin tests -n 4 -q -p no:cacheprovider \
  --cov=sqlglot --cov=tests --cov-report= 2>&1 | tail -15
