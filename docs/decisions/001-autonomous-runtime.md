# 001 — Autonomous runtime: isolated WSL2 distro, tiered models

**Date:** 2026-08-12
**Status:** accepted

## Context

The project is to be developed autonomously: an agent executes `PLAN.md` §9
across days with no human gate, restarted by an outer loop whenever its context
or session ends. This needs (a) a Linux build environment for crawl, (b) a
sandbox, since the agent runs with permission prompts disabled, and (c) a cost
structure that survives multi-day operation.

The host is Windows 11 (24 CPUs, 95 GB RAM, 752 GB free) with WSL2 and Docker
Desktop available. An existing `Ubuntu-24.04` WSL distro is in use as a
general-purpose agent workstation and holds cloud credentials (`.aws`, `.azure`)
and several agent configs.

## Choices

**1. Runtime: a dedicated WSL2 distro, not Docker and not the existing distro.**

Native Windows was rejected outright: no gcc/make, and a crawl console build
there means MSYS2 — a poor foundation for the §6 telemetry work.

Docker was rejected as redundant. Docker Desktop on Windows runs its engine on
WSL2 anyway, so a container adds image-build and in-container-auth friction for
isolation that a separate distro already provides.

The existing `Ubuntu-24.04` was rejected on blast radius: it holds cloud
credentials and mounts the whole Windows profile at `/mnt/c`.

Created `dcss-agent` (Ubuntu 24.04) at `C:\WSL\dcss-agent`, with
`/etc/wsl.conf` disabling `automount` and `interop` — the agent cannot see `C:\`
or the other distro. Work lives on ext4 at `~/work/dcss-automation`; `/mnt/c`
would also have been slow for a build-heavy workload.

**2. Model tiering rather than a local model.**

The goal was to limit spend by running a local model for the grind. Claude Code
routes to a custom endpoint via `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN`,
but Anthropic explicitly does not support routing it to non-Claude models
through a gateway, and this workload — unattended, tool-call-heavy, days long —
is exactly where weak tool-calling degrades silently instead of failing loudly,
corrupting the journal that all resumability depends on.

Instead: a cheaper `WORKER_MODEL` for implementation iterations and a stronger
`ORCH_MODEL` for a review pass every `ORCH_EVERY` iterations and on any stall.
Both, plus the gateway variables, are settings in `ops/config.env`, so switching
to a local endpoint later is a config edit rather than a rewrite.

**3. Brakes on the loop.**

A bare `while true` loop burns budget indefinitely in a stuck state. The
supervisor adds: an `ops/STOP` kill switch, per-iteration wall-clock timeout,
exponential backoff on error, an optional iteration cap, and a stall detector
that escalates to the orchestrator after `STALL_ESCALATE` commitless iterations
and halts after `STALL_HALT`.

## Reasoning

The failure mode that matters most is not the agent doing something destructive
— it is the agent making no progress while appearing to work. Hence the
commit-based stall detector, the "every iteration must leave a trace" rule in
`CLAUDE.md`, and the orchestrator pass whose explicit job is to catch a worker
declaring phases done on existence checks rather than `PLAN.md`'s acceptance
tests.

## Consequences

- Reviewing work means `wsl -d dcss-agent`, or reading GitHub. The Windows
  checkout at `C:\AgentWorkspaces\dcss-automation` is a read-only view kept in
  sync by `git pull`.
- Disposal is `wsl --unregister dcss-agent`; nothing outside the distro and the
  GitHub repo is touched.
- The distro needs its own Claude Code authentication and git push credential.
