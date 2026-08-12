# 007 — Archetype classification for the outcome-vector report

**Context:** PLAN.md §1 requires the collector's report to stratify by
"species, background, and archetype" but never defines what an archetype is
— there is no such field on a combo, a species, or a background anywhere in
crawl's own data. This has to be invented, not looked up.

**Choice:** classify each background (job) into one of four archetypes using
only objective fields already in the pinned crawl source
(`crawl-ref/source/job-data.h`, generated from `dat/jobs/*.yaml` — not
guessed from general DCSS knowledge, which drifts across versions):
whether the job has a `weapon_choice` other than `none`, and whether its
starting-spells list is non-empty.

| archetype | rule                                            | jobs (abbr)                                      |
|-----------|--------------------------------------------------|---------------------------------------------------|
| caster    | spells > 0, weapon_choice == none                | AE, Al, Cj, EE, En, FE, HW, Hs, IE, Ne, Su         |
| hybrid    | spells > 0, weapon_choice != none                | CA, Re, Wr                                         |
| melee     | spells == 0, weapon_choice != none                | Fi, Gl, Be, CK, Mo, De                             |
| utility   | spells == 0, weapon_choice == none                | Ar, Br, Hu, Sh, Wn                                 |

Verified this covers all 25 jobs in the current pinned manifest
(`data/manifests/legal-characters.json`) with no leftovers. Table is
hardcoded in `ops/collector.py` (`JOB_ARCHETYPE`); a job abbr not in the
table (e.g. after a re-pin adds/removes jobs) reports `archetype="unknown"`
rather than crashing, so a re-pin degrades gracefully instead of breaking
the collector.

**Reasoning:** "melee/caster/hybrid" is the closest thing to a standard
informal taxonomy DCSS players use, but doing it from memory would be
curation, not measurement, and would silently drift from whatever the
pinned commit's actual jobs are. Deriving it from the two structural fields
crawl already encodes (does this background start able to cast, does it
start with a weapon-choice) keeps the classification objective, re-derivable
from source, and revisable by editing one table if it turns out to be a bad
split (e.g. Enchanter — hexes+stabbing — lands as "caster" here since it has
no starting weapon choice, even though many players would call it a melee
hybrid in play; the split is by starting kit, not by how the class is
actually played, which is deliberately the more falsifiable definition of
the two).

**Rejected alternative:** leaving "archetype" out of the report entirely
until someone specifies it. Rejected because PLAN.md explicitly requires it
in Phase 1's exit criteria, and CLAUDE.md says decide and keep moving rather
than block on an ambiguity that has a defensible resolution.
