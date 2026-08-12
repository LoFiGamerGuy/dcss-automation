#!/usr/bin/env bash
#
# ops/supervise.sh — the outer loop.
#
# No agent runs forever: context windows fill, sessions end. This re-issues a
# re-entrant prompt so a fresh invocation picks up from docs/JOURNAL.md where
# the last one died. It is deliberately dumb; all the intelligence is in the
# journal protocol and the prompts.
#
#   Kill switch:  touch ops/STOP
#   Follow along: tail -f logs/supervisor/supervisor.log
#
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

# shellcheck source=/dev/null
source "$REPO_ROOT/ops/config.env"

STATE_DIR="$REPO_ROOT/ops/.state"
LOG_DIR="$REPO_ROOT/logs/supervisor"
mkdir -p "$STATE_DIR" "$LOG_DIR"

ITER_FILE="$STATE_DIR/iteration"
STALL_FILE="$STATE_DIR/stall"
[ -f "$ITER_FILE" ]  || echo 0 > "$ITER_FILE"
[ -f "$STALL_FILE" ] || echo 0 > "$STALL_FILE"
rm -f "$STATE_DIR/HALTED"

log() {
  printf '%s | %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" \
    | tee -a "$LOG_DIR/supervisor.log"
}

halt() {
  log "HALT: $*"
  printf '%s\nhalted at %s\n' "$*" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    > "$STATE_DIR/HALTED"
  exit 0
}

trap 'log "supervisor received SIGINT/SIGTERM; exiting"; exit 130' INT TERM

command -v claude >/dev/null 2>&1 || { echo "claude not on PATH" >&2; exit 1; }

log "supervisor start — worker=$WORKER_MODEL orch=$ORCH_MODEL every=$ORCH_EVERY pid=$$"

backoff=$SLEEP_BASE

while :; do
  [ -f "$REPO_ROOT/ops/STOP" ] && halt "ops/STOP present (kill switch)"

  iter=$(( $(cat "$ITER_FILE") + 1 ))
  echo "$iter" > "$ITER_FILE"

  if [ "$MAX_ITERATIONS" -gt 0 ] && [ "$iter" -gt "$MAX_ITERATIONS" ]; then
    halt "reached MAX_ITERATIONS=$MAX_ITERATIONS"
  fi

  stall=$(cat "$STALL_FILE")

  # Role selection: periodic review, or escalation because the worker is stuck.
  role="worker"; model="$WORKER_MODEL"; promptfile="PROMPT.md"
  if [ "$ORCH_EVERY" -gt 0 ] && [ $(( iter % ORCH_EVERY )) -eq 0 ]; then
    role="orchestrator"
  fi
  if [ "$stall" -ge "$STALL_ESCALATE" ]; then
    role="orchestrator"
  fi
  if [ "$role" = "orchestrator" ]; then
    model="$ORCH_MODEL"; promptfile="ORCHESTRATOR.md"
  fi

  git pull --ff-only --quiet 2>/dev/null || log "warn: git pull --ff-only failed (continuing)"
  before="$(git rev-parse HEAD)"

  logfile="$LOG_DIR/$(printf 'iter-%05d-%s' "$iter" "$role").log"
  log "iteration $iter role=$role model=$model stall=$stall -> $logfile"

  prompt="Read docs/JOURNAL.md, then continue the work per ${promptfile}. Follow CLAUDE.md. You are running unattended: do not ask for approval or preferences — decide, record the decision, and proceed."

  timeout --signal=INT --kill-after=60 "$ITER_TIMEOUT" \
    claude -p "$prompt" \
      --model "$model" \
      --permission-mode bypassPermissions \
      --output-format text \
      ${MAX_TURNS:+--max-turns "$MAX_TURNS"} \
      >>"$logfile" 2>&1
  rc=$?
  [ "$rc" -eq 124 ] && log "iteration $iter hit ITER_TIMEOUT (${ITER_TIMEOUT}s)"

  after="$(git rev-parse HEAD)"
  if [ "$before" = "$after" ]; then
    stall=$(( stall + 1 ))
    log "iteration $iter produced no commit (stall=$stall) rc=$rc"
  else
    stall=0
    log "iteration $iter committed $(git rev-list --count "$before".."$after") change(s) rc=$rc"
    git push --quiet 2>/dev/null || log "warn: push failed — check git credentials"
  fi
  echo "$stall" > "$STALL_FILE"

  if [ "$stall" -ge "$STALL_HALT" ]; then
    halt "no new commit for $stall consecutive iterations — needs a human look"
  fi

  if [ "$rc" -ne 0 ] && [ "$rc" -ne 124 ]; then
    log "backing off ${backoff}s after rc=$rc"
    sleep "$backoff"
    backoff=$(( backoff * 2 ))
    [ "$backoff" -gt "$SLEEP_MAX" ] && backoff=$SLEEP_MAX
  else
    backoff=$SLEEP_BASE
    sleep "$SLEEP_BASE"
  fi
done
