#!/usr/bin/env bash
#
# ops/overnight.sh — one command to stand up the local model and run overnight.
#
#   ops/overnight.sh            stand up, preflight, launch in tmux
#   ops/overnight.sh --check    run every check, launch nothing
#
# Worker runs on the local model via LM Studio; the orchestrator checks in on
# Fable every ORCH_EVERY iterations. The loop halts by itself after
# MAX_RUNTIME_HOURS (see ops/local.env).
#
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1
# Order matters: local.env assigns the profile, config.env fills in anything the
# profile left alone via ${VAR:-default}. Sourcing config.env first would make
# its defaults win and silently discard the profile (e.g. no runtime deadline).
# shellcheck source=/dev/null
source "$REPO_ROOT/ops/local.env"
# shellcheck source=/dev/null
source "$REPO_ROOT/ops/config.env"

CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

SESSION="${SESSION:-dcss-overnight}"
LOG_DIR="$REPO_ROOT/logs/supervisor"
mkdir -p "$LOG_DIR"

step() { printf '\n\033[1m[%s]\033[0m %s\n' "$1" "$2"; }
say()  { printf '  %s\n' "$*"; }
die()  { printf '\n\033[31mABORTED:\033[0m %s\n' "$*" >&2; exit 1; }

printf '\n=== dcss-automation — local-model overnight run ===\n'
say "worker:       $WORKER_MODEL  (local, via $WORKER_BASE_URL)"
say "orchestrator: $ORCH_MODEL  (real Claude API, every $ORCH_EVERY iterations)"
say "brakes:       max ${MAX_RUNTIME_HOURS}h, ${MAX_TURNS} turns/iteration, halt after $STALL_HALT commitless iterations"

# ---------------------------------------------------------------------------
step 1/6 "Starting the local gateway"
"$REPO_ROOT/ops/local-gateway.sh" start || die "gateway failed to start (see logs/gateway/litellm.log)"

# ---------------------------------------------------------------------------
step 2/6 "Testing Anthropic-format translation"
"$REPO_ROOT/ops/local-gateway.sh" test || die "the gateway is up but does not answer /v1/messages correctly"

# ---------------------------------------------------------------------------
# The check that actually matters. A model can chat fine and still be unable to
# drive Claude Code's tool loop — and a worker that cannot call tools produces
# plausible-looking journal entries describing work it never did, which is the
# one failure that quietly destroys a night's progress.
step 3/6 "Preflight: can the local model drive the tool loop?"
PROBE=/tmp/preflight_local.txt
rm -f "$PROBE"
PFLOG="$LOG_DIR/preflight.log"
timeout 900 env \
  "ANTHROPIC_BASE_URL=$WORKER_BASE_URL" \
  "ANTHROPIC_AUTH_TOKEN=$WORKER_AUTH_TOKEN" \
  "ANTHROPIC_DEFAULT_HAIKU_MODEL=$WORKER_SMALL_MODEL" \
  "ANTHROPIC_SMALL_FAST_MODEL=$WORKER_SMALL_MODEL" \
  "CLAUDE_CODE_MAX_CONTEXT_TOKENS=${WORKER_CONTEXT_TOKENS:-64000}" \
  claude -p "Use the Write tool to create the file $PROBE whose entire contents are the single word PREFLIGHT_OK. Then stop." \
    --model "$WORKER_MODEL" \
    --permission-mode bypassPermissions \
    --output-format text \
    --max-turns 10 >"$PFLOG" 2>&1
if grep -q 'PREFLIGHT_OK' "$PROBE" 2>/dev/null; then
  say "PASS — the local model wrote the file through the Write tool"
else
  say "FAIL — no valid $PROBE was produced. Transcript:"
  tail -25 "$PFLOG" | sed 's/^/    /'
  die "the local model cannot reliably drive tool calls. Running overnight on it would fill the journal with work that never happened. Fix the model/context settings in LM Studio, or run ops/supervise.sh on a Claude worker instead."
fi

# ---------------------------------------------------------------------------
step 4/6 "Checking the orchestrator can reach the real Claude API"
ORCHLOG="$LOG_DIR/orch-auth.log"
timeout 240 env -u ANTHROPIC_BASE_URL -u ANTHROPIC_AUTH_TOKEN \
  -u ANTHROPIC_DEFAULT_HAIKU_MODEL -u ANTHROPIC_SMALL_FAST_MODEL \
  claude -p "Reply with exactly: ORCH_OK" --model "$ORCH_MODEL" \
    --output-format text >"$ORCHLOG" 2>&1
if grep -q 'ORCH_OK' "$ORCHLOG"; then
  say "PASS — $ORCH_MODEL reachable"
else
  say "FAIL — $ORCH_MODEL did not answer. Output:"
  tail -10 "$ORCHLOG" | sed 's/^/    /'
  die "the orchestrator is the only thing checking the local worker's homework. Run 'claude' and /login, then retry."
fi

# ---------------------------------------------------------------------------
step 5/6 "Tagging a recovery point"
TAG="prelocal-$(date +%Y%m%d-%H%M)"
git tag -f "$TAG" >/dev/null 2>&1 && say "tagged $TAG at $(git rev-parse --short HEAD)"
say "if the night goes badly:  git reset --hard $TAG"

# ---------------------------------------------------------------------------
if [ "$CHECK_ONLY" = "1" ]; then
  printf '\n\033[1mAll checks passed.\033[0m Re-run without --check to launch.\n\n'
  exit 0
fi

step 6/6 "Launching the supervised loop"
rm -f "$REPO_ROOT/ops/STOP"
if tmux has-session -t "$SESSION" 2>/dev/null; then
  die "tmux session '$SESSION' already exists. Attach with: tmux attach -t $SESSION"
fi
tmux new-session -d -s "$SESSION" \
  "cd '$REPO_ROOT' && source ops/local.env && exec ops/supervise.sh"
sleep 3
tmux has-session -t "$SESSION" 2>/dev/null || die "tmux session died immediately — check $LOG_DIR/supervisor.log"
say "running in tmux session '$SESSION'"

cat <<EOF

=== running ===

  watch      tail -f logs/supervisor/supervisor.log
  attach     tmux attach -t $SESSION      (detach: Ctrl-b then d)
  stop       touch ops/STOP               (finishes the current iteration, then exits)
  hard stop  tmux kill-session -t $SESSION && ops/local-gateway.sh stop
  morning    git log --oneline; tail -60 docs/JOURNAL.md

It halts on its own after ${MAX_RUNTIME_HOURS}h, or after $STALL_HALT iterations
without a commit. The gateway keeps running after the loop stops; shut it down
with: ops/local-gateway.sh stop

EOF
