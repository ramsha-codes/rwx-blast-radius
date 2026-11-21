#!/bin/bash
export MSYS_NO_PATHCONV=1
cd /d/Buildathon-RWX
W="$(pwd -W)/work"; T="$(pwd -W)/tools"
docker run --rm --memory 3500m --cpus 4 -v "$W:/work" -v "$T:/tools:ro" rwx-cov-local sh /tools/isprof/val_run.sh 3 $(cat work/isprof/val_order.txt)
echo "VAL DONE $(date +%H:%M:%S)"
