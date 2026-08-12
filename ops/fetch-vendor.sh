#!/usr/bin/env bash
# Fetch vendor/{crawl,qw} at the exact commits pinned in ops/vendor-lock.json,
# then apply any overlay patches in patches/{crawl,qw}/*.patch. Idempotent:
# wipes and re-fetches each vendor dir every run, so it's always driven by
# the lock file, never by whatever happens to be on disk. See
# docs/decisions/002 and docs/decisions/003.
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

  # Shallow --depth 1 fetches carry no tags, so `git describe` (used by both
  # crawl's Makefile SRC_VERSION and qw's make-qw.sh) fails and yields an
  # empty version string. A local annotated tag on the pinned commit fixes
  # that without needing the full tag history. crawl's util/gen_ver.pl parses
  # this string against a version regex (X.Y[-alphaN]) and dies otherwise, so
  # the tag name must be per-repo, not a generic constant — see describe_tag
  # in vendor-lock.json.
  local describe_tag
  describe_tag=$(jq -r ".${name}.describe_tag" "$LOCK")
  git -C "$dest" tag -a "$describe_tag" -m "pinned by ops/vendor-lock.json" "$commit"
}

fetch_pin crawl
fetch_pin qw

apply_patches() {
  local name="$1"
  shopt -s nullglob
  local patches=("$ROOT"/patches/"$name"/*.patch)
  if [ ${#patches[@]} -gt 0 ]; then
    echo "== applying ${#patches[@]} $name patch(es) =="
    for p in "${patches[@]}"; do
      echo "  $p"
      git -C "$VENDOR/$name" apply --whitespace=nowarn "$p"
    done
  fi
}

apply_patches crawl
apply_patches qw

# qw ships its bot logic as many small lua files under source/; qw.rc only
# loads it if combined into qw.lua first (README.md "Method 1"). This isn't
# checked into the qw repo, so it must be (re)generated on every fetch for
# the vendor dir to be runnable, not just buildable.
( cd "$VENDOR/qw" && bash make-qw.sh )

echo "vendor fetch complete: $VENDOR/crawl @ $(git -C "$VENDOR/crawl" rev-parse --short HEAD), $VENDOR/qw @ $(git -C "$VENDOR/qw" rev-parse --short HEAD)"
