#!/usr/bin/env bash
# Fetch vendor/{crawl,qw} at the exact commits pinned in ops/vendor-lock.json,
# then apply any overlay patches in patches/qw/*.patch. Idempotent: wipes and
# re-fetches each vendor dir every run, so it's always driven by the lock
# file, never by whatever happens to be on disk. See docs/decisions/002.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK="$ROOT/ops/vendor-lock.json"
VENDOR="$ROOT/vendor"

if ! command -v jq >/dev/null 2>&1; then
  echo "fetch-vendor.sh: jq is required" >&2
  exit 1
fi

fetch_pin() {
  local name="$1"
  local repo commit dest
  repo=$(jq -r ".${name}.repo" "$LOCK")
  commit=$(jq -r ".${name}.commit" "$LOCK")
  dest="$VENDOR/$name"

  echo "== $name: $commit ($repo) =="
  rm -rf "$dest"
  mkdir -p "$dest"
  (
    cd "$dest"
    git init -q
    git remote add origin "$repo"
    if git fetch --depth 1 origin "$commit" -q 2>/tmp/fetch-vendor-$name.err; then
      git checkout -q FETCH_HEAD
    else
      echo "  shallow fetch of exact commit failed, falling back to full fetch:" >&2
      cat /tmp/fetch-vendor-$name.err >&2
      git fetch origin -q
      git checkout -q "$commit"
    fi
  )
  local actual
  actual=$(cd "$dest" && git rev-parse HEAD)
  if [ "$actual" != "$commit" ]; then
    echo "$name: expected $commit, got $actual" >&2
    exit 1
  fi
}

fetch_pin crawl
fetch_pin qw

shopt -s nullglob
patches=("$ROOT"/patches/qw/*.patch)
if [ ${#patches[@]} -gt 0 ]; then
  echo "== applying ${#patches[@]} qw patch(es) =="
  for p in "${patches[@]}"; do
    echo "  $p"
    git -C "$VENDOR/qw" apply --whitespace=nowarn "$p"
  done
fi

echo "vendor fetch complete: $VENDOR/crawl @ $(git -C "$VENDOR/crawl" rev-parse --short HEAD), $VENDOR/qw @ $(git -C "$VENDOR/qw" rev-parse --short HEAD)"
