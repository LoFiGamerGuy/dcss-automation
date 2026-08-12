# CLAUDE.md — operating conventions for dcss-automation

This file is auto-loaded on every invocation. It holds **conventions and
guardrails**. The standing work order is in [`PROMPT.md`](PROMPT.md); read it
every session.

## Autonomy

There is no human watching. Never pause to ask for approval, confirmation, or
preferences. Every decision you would ask about, decide yourself, record in
`docs/decisions/NNN-<topic>.md` (context / choice / reason — keep it short),
and keep moving.

## Source of truth

`PLAN.md` on `main` is canonical and reviewed. Execute §9 phases in order.
A phase's acceptance tests are the **only** gate between phases: tests pass →
proceed immediately; tests fail → fix and re-run.

Do not redesign the architecture. If reality contradicts the plan (a build flag
doesn't exist, a tool behaves differently), adapt with the smallest working
alternative, record a decision file, and continue. Do not stop to renegotiate.

## Resumability

`docs/JOURNAL.md` is your entire memory across invocations. If you are started
fresh, the journal plus repo state is all you have — trust it and continue from
its last **Next step**.

- **Read it first**, every session, before anything else.
- Append dated entries as you go: what you did, what passed/failed, and an
  explicit **Next step**.
- Write the *Next step* entry **before** attempting anything long or risky
  (builds, campaigns), not after.

## Every iteration must leave a trace

An invocation that ends having changed nothing is a failure, and it is the most
expensive failure mode here. Before you finish, you must have done at least one
of:

1. committed real progress, or
2. appended a journal entry stating what you attempted and why it did not
   produce a commit, or
3. written `docs/BLOCKED.md`.

## Git guardrails

- Develop directly on `main`. Commit and push after every completed work item,
  and **always before** any long-running operation.
- **Never** force-push, rebase published commits, `git reset --hard` on `main`,
  amend a pushed commit, or otherwise rewrite history.
- **Never** `git clean -xfd` outside directories you created yourself.
- Vendored deps (`crawl`, `qw`) are pinned to exact commits in a lock file per
  `PLAN.md` §5 — never track a branch.

## Long-running work

Builds take minutes; campaigns take hours. These do **not** run inside your
invocation.

- Start them detached (`nohup`/`setsid`, or a systemd user unit) with logging
  to `logs/`.
- Record the PID/unit and log path in the journal **before** starting.
- Then go do other work — write the collector, reports, or tests. Never idle-wait
  silently while a campaign runs.
- On a later invocation, check the log to see how it went.

## Failure handling

Diagnose and repair yourself: read logs, reduce the repro, try the documented
fallback (e.g. the `PLAN.md` §6 telemetry fallback). Only if something is truly
impossible without a human — credentials, hardware, a licensing wall — write
`docs/BLOCKED.md` saying what is blocked and exactly what is needed, commit it,
and **continue with whatever is not blocked**. One blocked item never stops the
others.

## Environment

- Runtime is the isolated WSL2 distro `dcss-agent` (Ubuntu 24.04). No access to
  the Windows filesystem — this is deliberate.
- Repo lives at `~/work/dcss-automation` on ext4.
- Build toolchain is preinstalled: gcc 13, make, ncursesw, lua5.1 headers,
  libsqlite3, zlib, bison, flex, python3-yaml.
- 24 CPUs, 46 GB RAM visible. Parallelize campaigns accordingly, but leave
  headroom — do not saturate all 24.
- `sudo` is passwordless if you need more packages.
