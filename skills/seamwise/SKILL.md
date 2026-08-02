---
name: seamwise
description: Orchestrate the complete Seamwise intent-to-task workflow through the installed `seamwise` CLI. Use when asked to initialize or resume a Seamwise workspace, turn delivery intent into a seam map, delivery plan, task graph, or Task-Specs, inspect gate status, or determine the next safe action.
---

# Seamwise

Drive the shared CLI; do not recreate compiler behavior in the model.

## Workflow

1. Confirm that `seamwise` is executable. If it is absent, stop and give the documented installation command; do not imitate its output.
2. Run `seamwise --json doctor`. Treat any nonzero exit as a blocker and report its diagnostics.
3. Resolve the intended workspace explicitly with the user when more than one candidate exists. Never silently initialize or switch workspaces.
4. Run `seamwise --workspace "<path>" --json status`, then follow only the ordered actions in `next`.
5. If mapping is next and no authored recipe exists, run `seamwise --workspace "<path>" --json recipe schema` and `seamwise --workspace "<path>" recipe example --output seamwise-recipe.yaml`. Replace every fixture fact with sourced project evidence; never present the bundled example as project truth.
6. Use `seamwise --workspace "<path>" --json prepare --source "<recipe.yaml>"` for the normal resumable path before mapping, or omit `--source` when the seam map already exists. Use the stage skills when the user asks to focus on one transformation.
7. Re-run `seamwise --workspace "<path>" --json status` and report the exact token, artifact paths, diagnostics, and next human decision.

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
