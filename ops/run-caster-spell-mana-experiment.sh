#!/usr/bin/env bash
set -euo pipefail
cd /home/agent/work/dcss-automation

echo "== control arm (bugfix off) =="
python3 ops/campaign.py --seeds-file data/experiments/caster-spell-mana-fix/seeds.json \
  --run-prefix exp-spellmana-control --disable-bugfix-spell-mana-check \
  --turn-budget 20000 --wall-cap-secs 900 --workers 16 \
  --runs-dir data/runs --out data/experiments/caster-spell-mana-fix/control-summary.json

echo "== treatment arm (bugfix on) =="
python3 ops/campaign.py --seeds-file data/experiments/caster-spell-mana-fix/seeds.json \
  --run-prefix exp-spellmana-treatment \
  --turn-budget 20000 --wall-cap-secs 900 --workers 16 \
  --runs-dir data/runs --out data/experiments/caster-spell-mana-fix/treatment-summary.json

echo "EXPERIMENT_DONE"
