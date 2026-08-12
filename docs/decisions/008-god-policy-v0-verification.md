# 008 — God policy v0: verified as already satisfied by qw's stock defaults

**Context.** PLAN.md §5 point 3 specifies a "god policy v0": zealots keep
their start god; otherwise a default `GOD_LIST = Okawaru/Trog/Makhleb`
(qw's strongest), with a per-species override table (Demigod → none,
called out explicitly as an example). `PROMPT.md`'s Phase 1 work list
names this as a deliverable separate from the sampler/rc-gen/runner/
collector pieces, which raised the question of whether `campaign.rc.tmpl`
needs to inject a per-species `GOD_LIST` override before the real
≥500-game campaign launches.

**Investigation (read qw's source, not assumed).** `vendor/qw/qw.rc:58`
already sets `GOD_LIST = { "Trog", "Okawaru", "Makhleb"}` as qw's own
default — identical to PLAN's specified default — and `campaign.rc.tmpl`
includes `qw.rc` unmodified and never overrides `GOD_LIST`, so every
campaign run already gets this default with zero extra code.

The two policy cases PLAN calls out are both already handled inside qw
itself, not by harness config:

- **Demigod → none.** `qw.lua`'s `want_god()` (the single gate that decides
  whether qw ever pursues god-seeking behavior at all) is:
  ```lua
  function want_god()
      return you.race() ~= "Demigod"
          and you.god() == "No God"
          and god_options()[1] ~= "No God"
  end
  ```
  `you.race() ~= "Demigod"` is a hardcoded exclusion — qw never seeks an
  altar or attempts conversion for a Demigod character, regardless of
  `GOD_LIST`. Cross-checked against the engine side:
  `religion.cc:player_can_join_god()` returns `false` unconditionally when
  `you.has_mutation(MUT_FORLORN)`, and `tags.cc:3497` fixes `MUT_FORLORN`
  for `SP_DEMIGOD` specifically (`SP_MUT_FIX(MUT_FORLORN, SP_DEMIGOD)`) —
  grepped every `SP_MUT_FIX(MUT_FORLORN, ...)` call site in `tags.cc` and
  Demigod is the *only* species with this fixed mutation in the pinned
  source, so no other species in the legal-character manifest needs an
  override for this reason.
- **Zealots keep their start god.** `want_god()`'s second condition,
  `you.god() == "No God"`, already excludes any character that starts
  with a god assigned (every zealot background) — the god-list logic is
  simply never consulted for them, so their start god is never touched by
  construction, with no zealot-specific code needed on either side.

Both cases were already implicitly exercised by Phase 0's canary suite
(`HuCK` zealot, `FeSu`/caster among others) without incident, consistent
with this finding — those canaries just weren't specifically read for
god-policy correctness at the time.

**Decision.** No harness code change needed for god policy v0. Leaving
`campaign.rc.tmpl` as-is (no explicit `GOD_LIST` override) is correct: it
inherits qw's stock default, which already matches PLAN's spec, and qw's
own `want_god()` already implements both special cases PLAN names. This
note exists so a future session doesn't rediscover the same question and
assume the gap is real — it's verified closed, not merely assumed closed.

**If this ever needs revisiting:** a future species added to the pinned
manifest with its own worship restriction, or a desire to change the
*default* three-god list itself, would be the trigger — grep
`tags.cc` for `SP_MUT_FIX(MUT_FORLORN, ...)` against the manifest's
current species list to re-check the first case.
