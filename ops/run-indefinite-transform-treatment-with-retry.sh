#!/usr/bin/env bash
# Treatment arm of the indefinite-transform-bugfix experiment, with retry.
#
# docs/decisions/013: a real, intermittent "no 'Welcome,' banner within 60s"
# harness_failure hits every run in a campaign.py batch, unpredictably --
# confirmed not tied to job-list size, relative-vs-absolute paths, chunking,
# fork-vs-spawn, or any single character/seed (multiple full-scale attempts
# both failed 100% and succeeded 100% with no code difference between some
# of them). Root cause not pinned down. Since it's a startup-time race, not
# reproducible-per-character, retrying purged failures is a legitimate
# mitigation: a character that hit the race once has no special reason to
# hit it again.
set -euo pipefail
cd /home/agent/work/dcss-automation

MAX_ATTEMPTS=6
RUN_PREFIX=exp-transform-treatment

for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
  echo "== attempt $attempt/$MAX_ATTEMPTS =="
  python3 ops/campaign.py \
    --seeds-file data/experiments/indefinite-transform-bugfix/seeds.json \
    --run-prefix "$RUN_PREFIX" \
    --turn-budget 20000 --wall-cap-secs 900 --workers 16 \
    --runs-dir data/runs \
    --out data/experiments/indefinite-transform-bugfix/treatment-summary.json

  purge_out=$(python3 ops/purge-welcome-timeout-failures.py \
    --runs-dir data/runs --run-prefix "$RUN_PREFIX")
  echo "$purge_out"
  purged_n=$(echo "$purge_out" | head -1 | grep -oE '[0-9]+' | head -1)

  if [ "$purged_n" -eq 0 ]; then
    echo "== no welcome-timeout failures left, done =="
    break
  fi
  if [ "$attempt" -eq "$MAX_ATTEMPTS" ]; then
    echo "== retry budget exhausted, $purged_n run(s) still purged-and-unretried =="
  fi
done

echo "EXPERIMENT_DONE"
