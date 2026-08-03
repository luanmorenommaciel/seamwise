---
name: seamwise
description: Orchestrate the complete Seamwise intent-to-task workflow through the installed `seamwise` CLI. Use when asked to initialize or resume a Seamwise workspace, turn delivery intent into a seam map, delivery plan, task graph, or Task-Specs, inspect gate status, or determine the next safe action.
---

# Seamwise

Drive the shared CLI; do not recreate compiler behavior in the model.

## First run

1. Check whether `seamwise` is executable.
2. If it is absent and the user explicitly asked to install Seamwise, confirm `uv` is available and run `uv tool install "git+https://github.com/luanmorenommaciel/seamwise.git"`. If installation was not explicitly requested, offer that exact command and wait. Never imitate CLI output.
3. Run `seamwise --json doctor`. Treat any nonzero exit as a blocker and report its diagnostics.
4. Resolve the intended workspace explicitly when more than one candidate exists. Never silently initialize or switch workspaces.

## Guided workflow

Default to one pass per human confirmation. Ask exactly one concise unanswered question at a time.

1. Run `seamwise --workspace "<path>" --json status` and report the current token and first `next` action.
2. If the workspace is absent, ask permission to initialize it, then run only `seamwise --workspace "<path>" --json init`.
3. Before mapping, run `seamwise --workspace "<path>" --json agent-context --host <codex|claude|chat>`. Follow its `guided-one-pass` authoring sequence and exact recipe schema. Build `seamwise-recipe.yaml` only from confirmed answers and immutable local evidence; do not use or invent an example.
4. Present the proposed Delivery Intent, evidence/system map, seams/ownership, capability/proof chain, and task contracts one pass at a time. Wait for explicit confirmation after each pass.
5. Run exactly one transformation after its input is confirmed: `map`, then `plan`, then explicit human `review`, then `compile`, then `tasks validate`. Report the exact JSON token and artifacts before asking whether to continue.
6. Use `prepare` only when the user explicitly asks for automation across already-confirmed passes. It still stops at closed gates and never reviews, preflights, or seals.
7. Re-run `status` at handoff and report the exact token, artifact paths, diagnostics, and next human decision.

Inspect `seamwise <command> --help` before using an option that is not shown here.

## Trust boundary

- Treat model-written material as a proposal until the CLI validates it.
- Treat `ok: true` plus the expected ready token as machine validation, not human acceptance, implementation proof, or Task-Spec sealing.
- Keep `current`, `proposed`, `derived`, and `external` claims distinct.
- Keep one accepted seam owned by exactly one swimlane. Name capability legs as observable states, not activities.
- Stop when evidence, ownership, architecture decisions, lineage, review, or proof boundaries are insufficient. Surface the CLI's diagnostics instead of inventing missing facts.
- Never auto-approve a review or run `seamwise tasks seal`. Sealing requires an explicit human request after successful validation and preflight.
- Never execute generated tasks or claim repository behavior was implemented merely because compilation succeeded.

For unsupported chat surfaces, generate the bounded packet with `seamwise --workspace "<path>" --json agent-context --host chat`. State that the packet can guide proposals but cannot prove local execution or validation.
