#!/usr/bin/env bash
# Generate and archive the legal-character manifest (PLAN.md §2) from the
# pinned, built crawl binary: playable (species, background) pairs via
# -playable-json, and per-combo starting-weapon option sets via -weapon-json
# (a small crawl patch — see docs/decisions/003 — since no stock flag covers
# this). Output is the sampler's ground truth: its support set must exactly
# equal what this script archives (Phase 0 diff-test acceptance criterion).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CRAWL_BIN="$ROOT/vendor/crawl/crawl-ref/source/crawl"
OUT_DIR="$ROOT/data/manifests"

if [ ! -x "$CRAWL_BIN" ]; then
  echo "generate-manifest.sh: $CRAWL_BIN not found or not executable; build it first" >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "generate-manifest.sh: jq is required" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"

playable_json=$("$CRAWL_BIN" -playable-json)
weapon_json=$("$CRAWL_BIN" -weapon-json)
crawl_commit=$(git -C "$ROOT/vendor/crawl" rev-parse HEAD)
crawl_version=$("$CRAWL_BIN" -version | head -1 | sed -E 's/^Crawl version //')

jq -n \
  --argjson playable "$playable_json" \
  --argjson weapons "$weapon_json" \
  --arg crawl_commit "$crawl_commit" \
  --arg crawl_version "$crawl_version" \
  '{
    crawl_commit: $crawl_commit,
    crawl_version: $crawl_version,
    species: $playable.species,
    jobs: $playable.jobs,
    combos: $playable.combos,
    weapon_choices: $weapons
  }' > "$OUT_DIR/legal-characters.json"

sha256sum "$OUT_DIR/legal-characters.json" | awk '{print $1}' > "$OUT_DIR/legal-characters.json.sha256"

n_species=$(jq '.species | length' "$OUT_DIR/legal-characters.json")
n_jobs=$(jq '.jobs | length' "$OUT_DIR/legal-characters.json")
n_combos=$(jq '.combos | length' "$OUT_DIR/legal-characters.json")
n_weapon_combos=$(jq '.weapon_choices | length' "$OUT_DIR/legal-characters.json")

echo "manifest written: $OUT_DIR/legal-characters.json"
echo "  crawl @ ${crawl_commit:0:7} ($crawl_version)"
echo "  species=$n_species jobs=$n_jobs combos=$n_combos weapon_choice_combos=$n_weapon_combos"
echo "  sha256=$(cat "$OUT_DIR/legal-characters.json.sha256")"
