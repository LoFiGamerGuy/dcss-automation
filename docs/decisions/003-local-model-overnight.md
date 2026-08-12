# 003 — Local-model overnight profile

**Date:** 2026-08-12
**Status:** accepted (with a measured caveat)

## Context

Running the worker on a cloud Claude model continuously costs real money. The
goal was to run the grind on a local model overnight while keeping periodic
check-ins from a strong model.

Available hardware: RTX 5090 Laptop (24 GB VRAM), LM Studio on the Windows host
serving `qwen/qwen3.6-35b-a3b` (35B MoE, 3B active, 64k context) on port 1234.

## Choice

Worker on the local model via LM Studio; orchestrator stays on Fable via the
real Claude API, every 4 iterations instead of the cloud profile's 8.

`ANTHROPIC_BASE_URL` is process-global, so the supervisor applies routing
**per invocation** rather than exporting it once — otherwise the orchestrator
would also be routed to the local model and there would be nothing checking the
worker's work.

Anthropic does not support routing Claude Code to non-Claude models. This
profile is therefore treated as an experiment with a recovery tag
(`prelocal-<timestamp>`), a hard preflight gate, and more frequent supervision —
not as a supported configuration.

## What had to be fixed to make it work at all

Each of these was found by running Claude Code against the model end to end, and
each failed *silently* in a way that looked like something else:

1. **LiteLLM drops tool-call arguments when streaming.** Its Anthropic
   translation emits `content_block_start` with `"input": {}` followed by
   `content_block_stop`, and never the `input_json_delta` events carrying the
   arguments. Claude Code always streams, so every tool call arrived empty and
   the agent burned all its turns on `InputValidationError`. Fixed with
   `model_info.supports_native_streaming: false`, which calls the backend
   non-streaming (where arguments survive) and synthesizes the stream.
   `fake_stream: true` does **not** fix it. LM Studio itself streams correctly —
   the defect is entirely in the translation layer.

2. **Context window.** Claude Code assumes 200k for a model name it does not
   recognize, so it would not compact before the 64k backend overflowed. The
   real window is passed as `CLAUDE_CODE_MAX_CONTEXT_TOKENS`.

3. **Reasoning tokens.** This model spends 100+ tokens thinking before emitting
   any content — a 64-token budget returns an empty content block, which reads
   as a translation failure. Test budgets must be generous.

4. **LiteLLM dependency pins.** litellm 1.96.2 does not import against
   fastapi ≥0.116 (`get_flat_dependant` was removed), and sse-starlette 3.x then
   demands a newer starlette than fastapi <0.116 allows. Pinned
   `fastapi<0.116` + `sse-starlette<3` in `ops/local-gateway.sh setup`.

5. **Override precedence.** `config.env` fills defaults with `${VAR:-default}`,
   so it must be sourced *after* `local.env`. Sourced first, its defaults won and
   silently discarded the profile — the overnight run would have had no runtime
   deadline at all.

## Reasoning

The failure mode that justifies the preflight gate: a model that cannot reliably
call tools still produces fluent prose. It will write journal entries describing
work it never did, and since the journal is the only thing making the loop
resumable, that corrupts the one artifact everything else depends on. So
`ops/overnight.sh` refuses to launch unless the local model has actually created
a file through the `Write` tool in that session.

## Consequences

- `ops/overnight.sh` is the single entry point: gateway up → translation test →
  tool-loop preflight → orchestrator auth check → recovery tag → tmux launch.
- The loop halts on its own after 10h, or after 4 commitless iterations.
- Quality of local-model output over a long autonomous run is **unmeasured**.
  The preflight proves capability, not sustained reliability. The first morning
  after a local run, read `docs/JOURNAL.md` against `git log` and confirm the
  entries describe work that actually landed.
- Recovery is `git reset --hard prelocal-<timestamp>`.
