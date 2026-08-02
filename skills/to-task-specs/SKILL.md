---
name: to-task-specs
description: Materialize and validate runnable Task-Spec leaves from a ready Seamwise task graph through the shared CLI and bundled Task Pack. Use when asked to emit Task-Spec files, validate proof contracts, run preflight, inspect Task Pack diagnostics, or prepare explicitly authorized specs for sealing.
---

# To Task Specs

Use the `seamwise tasks` wrapper so every host reaches the same Task Pack behavior.

## Workflow

1. Run `seamwise --workspace "<path>" --json status`. Stop unless the task graph is ready and lineage is current.
2. Run `seamwise --workspace "<path>" --json tasks emit` to materialize drafts.
3. Run `seamwise --workspace "<path>" --json tasks validate`.
4. Review every authored eval body, then run `seamwise --workspace "<path>" --json tasks preflight --acknowledge-eval-execution` only when the user asks to prove execution readiness and explicitly authorizes those evals to execute in the workspace. Use global `--dry-run` first for structural and shellcheck-only preview without eval execution.
5. Report both the `TASK_SPECS=*` wrapper token and underlying Task Pack diagnostics. Treat `TASK_SPECS=VALID` or `TASK_SPECS=PREFLIGHT_READY` as validation only, never as execution or acceptance.
6. Run `seamwise --workspace "<path>" --json tasks seal --reviewer "<human>" --acknowledge-eval-execution --acknowledge-dispatch-authority` only after an explicit human request names the validated specs, authorizes one pinned Task Pack stamping gate to execute their evals according to Task Pack semantics, and all required preflight evidence is current. Never seal as part of ordinary compilation, and never seal a fixture review.

Keep XL and XXL items as composition nodes without write surfaces. Require each runnable leaf to have one coherent independently provable done-condition, explicit scope, verification, failure route, and lineage. Stop on stale hashes, tamper evidence, collisions, ambiguous proof, or unavailable providers; do not weaken a gate to obtain a green token.
