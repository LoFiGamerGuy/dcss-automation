#!/usr/bin/env bash
set -euo pipefail
cd /home/agent/work/dcss-automation

echo "== control arm (bugfix off) =="
python3 ops/campaign.py --seeds-file data/experiments/lua-error-bugfix/seeds.json \
  --run-prefix exp-luafix-control --disable-bugfix-lua-errors \
  --turn-budget 20000 --wall-cap-secs 900 --workers 16 \
  --runs-dir data/runs --out data/experiments/lua-error-bugfix/control-summary.json

echo "== treatment arm (bugfix on) =="
python3 ops/campaign.py --seeds-file data/experiments/lua-error-bugfix/seeds.json \
  --run-prefix exp-luafix-treatment \
  --turn-budget 20000 --wall-cap-secs 900 --workers 16 \
  --runs-dir data/runs --out data/experiments/lua-error-bugfix/treatment-summary.json

echo "EXPERIMENT_DONE"
