#!/usr/bin/env python3
"""Randomness contract sampler (PLAN.md §2, `uniform-pairs` default treatment).

Given the archived legal-character manifest (data/manifests/legal-characters.json,
generated from the pinned binary by generate-manifest.sh) and a dedicated
character-RNG seed, deterministically samples one (species, background) pair
uniformly, then — if that background offers a starting-weapon choice — a
weapon uniformly over that combo's legal options (§2 steps 1-3). The caller
supplies `char_seed` explicitly and separately from the game seed (§2 step 2:
"a dedicated character-RNG ... separate from the game seed") — this module
never touches the game seed at all, by design, so the two can't be conflated
by accident.

Library use: `sample_character(manifest, digest, char_seed)`.
CLI use: `combos.py --char-seed N` prints the sampled character as JSON,
including the exact `combo=` value to drop into a generated rc file (see
ops/canary/canary.rc.tmpl for the rc mechanism this feeds).
"""
import argparse
import hashlib
import json
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "data/manifests/legal-characters.json"


def load_manifest(path=MANIFEST_PATH):
    text = pathlib.Path(path).read_text()
    digest = hashlib.sha256(text.encode()).hexdigest()
    return json.loads(text), digest


def weapon_index(manifest):
    """combo abbr -> legal starting weapons, for combos that offer a choice."""
    return {w["combo"]: w["weapons"] for w in manifest["weapon_choices"]}


def sample_character(manifest, digest, char_seed, weapon_lookup=None):
    """Uniform-pairs sample (§2 steps 1-3). Deterministic in (manifest, char_seed)."""
    if weapon_lookup is None:
        weapon_lookup = weapon_index(manifest)
    combos = manifest["combos"]
    rng = random.Random(char_seed)

    pair_index = rng.randrange(len(combos))
    combo = combos[pair_index]

    weapons = weapon_lookup.get(combo)
    weapon_index_ = None
    weapon = None
    if weapons:
        weapon_index_ = rng.randrange(len(weapons))
        weapon = weapons[weapon_index_]

    rc_combo = f"{combo}.{weapon}" if weapon else combo

    return {
        "manifest_sha256": digest,
        "char_seed": char_seed,
        "pair_index": pair_index,
        "combo": combo,
        "weapon_index": weapon_index_,
        "weapon": weapon,
        "rc_combo": rc_combo,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--char-seed", type=int, required=True,
                     help="dedicated character-RNG seed (never the game seed)")
    ap.add_argument("--manifest", default=str(MANIFEST_PATH))
    args = ap.parse_args()

    if not pathlib.Path(args.manifest).exists():
        print(f"combos.py: manifest not found: {args.manifest}", file=sys.stderr)
        sys.exit(1)

    manifest, digest = load_manifest(args.manifest)
    print(json.dumps(sample_character(manifest, digest, args.char_seed)))


if __name__ == "__main__":
    main()
