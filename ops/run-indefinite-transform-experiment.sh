#!/usr/bin/env bash
set -euo pipefail
cd /home/agent/work/dcss-automation

echo "== control arm (bugfix off) =="
python3 ops/campaign.py --seeds-file data/experiments/indefinite-transform-bugfix/seeds.json \
  --run-prefix exp-transform-control --disable-bugfix-indefinite-transform \
  --turn-budget 20000 --wall-cap-secs 900 --workers 16 \
  --runs-dir data/runs --out data/experiments/indefinite-transform-bugfix/control-summary.json

echo "== treatment arm (bugfix on) =="
python3 ops/campaign.py --seeds-file data/experiments/indefinite-transform-bugfix/seeds.json \
  --run-prefix exp-transform-treatment \
  --turn-budget 20000 --wall-cap-secs 900 --workers 16 \
  --runs-dir data/runs --out data/experiments/indefinite-transform-bugfix/treatment-summary.json

echo "EXPERIMENT_DONE"
