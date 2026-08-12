#!/usr/bin/env bash
#
# ops/install-service.sh — run the supervisor as a systemd user service.
#
# Without this the loop is a child of whatever terminal started it, and dies
# when that terminal closes. As a lingering user service it survives logout and
# starts again on its own whenever the distro boots.
#
#   ops/install-service.sh          install + enable + start
#   ops/install-service.sh status   where it stands
#   ops/install-service.sh remove   stop + disable + delete the unit
#
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_NAME="dcss-supervisor.service"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT_PATH="$UNIT_DIR/$UNIT_NAME"

say() { printf '  %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

[ "$(ps -p 1 -o comm=)" = "systemd" ] || die "systemd is not PID 1 in this distro; use tmux instead"

case "${1:-install}" in
  install)
    # Lingering is what lets the service run without an active login session,
    # and start automatically when the distro boots.
    if ! loginctl show-user "$USER" -p Linger 2>/dev/null | grep -q 'Linger=yes'; then
      say "enabling lingering for $USER (needs sudo)"
      sudo loginctl enable-linger "$USER" || die "could not enable lingering"
    fi
    say "lingering: enabled"

    mkdir -p "$UNIT_DIR" "$REPO_ROOT/logs/supervisor"
    sed "s#%h#$HOME#g" "$REPO_ROOT/ops/dcss-supervisor.service" > "$UNIT_PATH"
    say "wrote $UNIT_PATH"

    if pgrep -f 'bash .*ops/supervise.sh' >/dev/null 2>&1; then
      die "a supervisor is already running outside systemd (pid $(pgrep -f 'bash .*ops/supervise.sh' | head -1)). Stop it first: touch ops/STOP, wait for it to exit, then re-run this."
    fi

    rm -f "$REPO_ROOT/ops/STOP"
    systemctl --user daemon-reload
    systemctl --user enable --now "$UNIT_NAME" || die "failed to start the service"
    sleep 3
    systemctl --user --no-pager --lines=0 status "$UNIT_NAME" | head -5
    cat <<EOF

  installed and running.

    follow    journalctl --user -u $UNIT_NAME -f
              tail -f logs/supervisor/supervisor.log
    stop      touch ops/STOP          (clean: finishes the current iteration)
    restart   systemctl --user restart $UNIT_NAME
    disable   ops/install-service.sh remove

EOF
    ;;

  status)
    systemctl --user --no-pager status "$UNIT_NAME" | head -12
    say "lingering: $(loginctl show-user "$USER" -p Linger 2>/dev/null || echo unknown)"
    ;;

  remove)
    systemctl --user disable --now "$UNIT_NAME" 2>/dev/null
    rm -f "$UNIT_PATH"
    systemctl --user daemon-reload
    say "removed $UNIT_NAME (lingering left enabled; disable with: sudo loginctl disable-linger $USER)"
    ;;

  *) echo "usage: $0 {install|status|remove}" >&2; exit 2 ;;
esac
