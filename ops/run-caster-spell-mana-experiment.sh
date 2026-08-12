#!/usr/bin/env bash
set -euo pipefail
cd /home/agent/work/dcss-automation

echo "== control arm (bugfix off) =="
python3 ops/campaign.py --seeds-file data/experiments/caster-spell-mana-fix/seeds.json \
  --run-prefix exp-spellmana-control --disable-bugfix-spell-mana-check \
  --turn-budget 20000 --wall-cap-secs 900 --workers 16 \
  --runs-dir data/runs --out data/experiments/caster-spell-mana-fix/control-summary.json

echo "== treatment arm (bugfix on) =="
# Prefix is "...-treat", not "...-treatment": run_id becomes crawl's -name,
# capped at 30 chars (docs/decisions/016). "exp-spellmana-treatment-NNNNNNN"
# is 31 chars and every such run hangs at crawl's startup menu; rc-gen.py now
# hard-errors on overlong run_ids. Collector queries must use
# run_id LIKE 'exp-spellmana-treat-%'.
python3 ops/campaign.py --seeds-file data/experiments/caster-spell-mana-fix/seeds.json \
  --run-prefix exp-spellmana-treat \
  --turn-budget 20000 --wall-cap-secs 900 --workers 16 \
  --runs-dir data/runs --out data/experiments/caster-spell-mana-fix/treatment-summary.json

echo "EXPERIMENT_DONE"
