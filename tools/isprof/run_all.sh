#!/bin/bash
export MSYS_NO_PATHCONV=1
cd /d/Buildathon-RWX
W="$(pwd -W)/work"; T="$(pwd -W)/tools"
for job in "base 0" "inst 1" "inst 2"; do
  set -- $job
  docker run --rm --memory 3500m --cpus 4 -v "$W:/work" -v "$T:/tools:ro" rwx-cov-local sh /tools/isprof/run_full.sh $1 $2
  echo "done $1 $2 $(date +%H:%M:%S)"
done
