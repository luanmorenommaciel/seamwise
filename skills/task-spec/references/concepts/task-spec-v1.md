# Task-Spec — The Format Specification

> **Current version:** v3.1 (stable)
> **First published:** 2026-05-19 (v1)
> **Format Owner:** task-spec CAW
> **Adopters:** anthive, taskship, AgentSpec, overnight-builder, Claude /goal, Codex, Kimi

The atomic, vendor-portable, self-verifying unit of work for autonomous agentic systems.

> **Note:** This document is the living format spec. It retains the `task-spec-v1.md`
> filename for link stability but describes the **current v3 format**. See the
> Version History section at the end for what changed across v0 → v1 → v2 → v3.
>
> **v3 quick map:** the format now scales by `profile`
> ([profiles.md](profiles.md): `lite | standard | full`), adds a **Behavior**
> zone whose `B-N` statements are traced to evals via `verifies:`, certifies
> executors by **conformance level** ([conformance-levels.md](conformance-levels.md):
> L0/L1/L2), supports one-level **decomposition** of FEATURE-altitude intent into
> gateable atoms ([decomposition.md](decomposition.md)), and closes the loop with a
> POST-execution **accept-task gate** (`accept-task.sh` → `accepted: true`)
> layered on the pre-dispatch sign-off gate ([signed-off.md](signed-off.md)).

---

## What is Task-Spec?

A **Task-Spec** is a markdown file that fully specifies one PR's worth of work
in a format any agentic tool can pick up and execute. It carries its own
verification rules — agents don't need humans to tell them whether they
succeeded.

The format has **five non-negotiable properties**:

1. **Atomic** — one Task-Spec = one PR's worth of work (S/M effort only)
2. **Vendor-portable** — works in any conformant engine (e.g. Claude, Codex, Cursor — adapters in runbooks/dispatch-recipes/) or manual execution
3. **Self-verifying** — runnable bash evals declare "done" mechanically
4. **Pickupable** — fully specified at authoring time; no further input needed
5. **Reportable** — machine-checkable pass/fail emit

A Task-Spec fails to be a Task-Spec if it lacks any of these. That's enforced by `validate-task-spec.sh`.

The **canonical anatomy** is the six-zone structure (Intent, Behavior, Contract,
Guardrails, Operations, and — on the `full` profile — Rollback + Observability) —
see [six-zones.md](six-zones.md) for the zone-by-zone deep dive. The v2
`agent_contract` schema (cross-vendor, with `required_tools` / `timeout_minutes` /
`sandbox_type`) is documented in [agent-contract.md](agent-contract.md).

---

## File anatomy

A Task-Spec is a single markdown file:

```text
tasks/T-YYYYMMDD-<slug>.md
```

Composed of **YAML frontmatter + the six-zone model** (the irreducible core —
Intent's Goal + Contract's runnable Success Criteria + Exit Check — is present at
every profile; the surrounding zones scale with `profile`):

```text
┌─ YAML FRONTMATTER ─────────────────────────────────────┐
│ Machine-parseable metadata                              │
└────────────────────────────────────────────────────────┘
┌─ ZONE 1 — INTENT ──────────────────────────────────────┐
│ Why this task exists (lean, ~100 lines max)             │
└────────────────────────────────────────────────────────┘
┌─ ZONE 2 — BEHAVIOR ────────────────────────────────────┐
│ B-N Given/When/Then; each verified by ≥1 eval          │
└────────────────────────────────────────────────────────┘
┌─ ZONE 3 — CONTRACT (the moat) ─────────────────────────┐
│ Runnable success criteria (verifies: [B-N]) +          │
│ validation card + exit check + agent output contract   │
└────────────────────────────────────────────────────────┘
┌─ ZONE 4 — GUARDRAILS ──────────────────────────────────┐
│ Anti-patterns, do-not-touch list                       │
└────────────────────────────────────────────────────────┘
┌─ ZONE 5 — OPERATIONS ──────────────────────────────────┐
│ Open questions, deferred decisions                     │
└────────────────────────────────────────────────────────┘
┌─ ZONE 6 — REVERSAL & RUNTIME (full profile) ───────────┐
│ Rollback Plan + Observability Hooks                    │
└────────────────────────────────────────────────────────┘
```

The full zone-by-zone anatomy (including the Behavior ↔ eval traceability chain)
lives in [six-zones.md](six-zones.md). Which zones are *required* is set by
`profile` ([profiles.md](profiles.md)): `lite` needs only the irreducible core;
`standard` adds Behavior + Context + Guardrails + Operations; `full` additionally
requires the Rollback Plan and Observability Hooks. Empty required zones are
allowed (use `(none)`); an omitted required zone is a validation error.

---

## YAML Frontmatter — Required Fields

```yaml
---
id: T-20260519-verify-langfuse-otel
title: Verify self-hosted Langfuse stack ingests anthive OTEL traces end-to-end
status: ready
effort: S
budget_iterations: 15
agent: any
depends_on: []
touches_paths:
  - docs/observability-runbook.md
  - docker/langfuse-compose.yml
source_note: notes/2026-05-04-observability-handoff.md
created: 2026-05-19T00:00:00-0300
tags: ["observability", "verification", "langfuse"]
---
```

### Field reference

| Field | Type | Required | Validation rule |
|-------|------|----------|-----------------|
| `id` | string | yes | Format: `T-YYYYMMDD-<kebab-slug>`. Deterministic, unique within `tasks/`. |
| `title` | string | yes | Single line, ≤120 chars. Imperative voice preferred ("Verify X" not "Verifying X"). |
| `status` | enum | yes | One of: `ready`, `in-progress`, `blocked`, `done`, `parked`. |
| `effort` | enum | yes | Six-tier: `XS`/`S`/`M`/`L` are runnable leaves (write-surface budget-checked; `L` needs `execution_backend: glm`); `XL`/`XXL` are NODES that MUST carry a `children:` block and decompose (no route out). See effort-gate.md. |
| `budget_iterations` | int | yes | Max retry cycles in the eval loop. Default 15. Hard cap 30. |
| `agent` | string | yes | `any` (vendor-portable) OR specific agent name (`python-developer`, `tsys-adf-parser`, etc.). |
| `depends_on` | list[string] | yes | List of Task-Spec IDs that must complete before this one. Empty `[]` if none. |
| `touches_paths` | list[string] | yes | Glob patterns of files this task WILL modify. Used for parallel-safety classification. |
| `source_note` | string | yes | Path to originating doc (meeting note, audit report). Provenance is non-optional. |
| `created` | ISO8601 | yes | Timestamp of authoring. Sortable, auditable. |
| `tags` | list[string] | no | Free-form labels for backlog navigation. |

Optional frontmatter fields:

| Field | Type | When to use |
|-------|------|-------------|
| `blocks` | list[string] | Inverse of `depends_on`; lists tasks blocked by this one |
| `source_action_item` | string | Specific item from `source_note` (e.g., "AI #6") |
| `precondition` | string | External event needed (not a task — e.g., "spec must be checked in") |
| `owner` | string | Human accountable for review |

---

## Zone 1 — Intent

```markdown
> **Why:** [1-2 sentences explaining why this task exists. Always present.]

## Goal

[One paragraph: what does success look like? Concrete, not aspirational.]

## Context

[Lean — max ~100 lines. Link to existing docs instead of duplicating.
This is NOT a PRD. Background only. The Contract zone does the heavy lifting.]
```

**Anti-pattern**: Verbose context dumps. If Zone 1 is longer than the Behavior +
Contract zones, you've written a PRD instead of a Task-Spec. Trim Zone 1; rely on
Zone 2's behaviors and Zone 3's evals to specify what "done" means.

---

## Zone 2 — Behavior

Behavior states *what the system must do* in observable Given/When/Then terms,
independent of how it's built. Each statement is labelled `B-N` and is the anchor
that Zone 3's evals trace back to.

```markdown
## Behaviors

- **B-1** — GIVEN the Langfuse stack is running
  WHEN a trace is emitted with resource attributes
  THEN it appears in the UI within 30 seconds with those attributes intact.
- **B-2** — GIVEN a fresh checkout
  WHEN an operator follows the runbook
  THEN the stack reaches a healthy state with no manual edits.
```

### The traceability rule (bidirectional)

Behavior and verification are two halves of one contract; neither may dangle:

1. **Every `B-N` is verified by ≥1 eval** whose validation-card entry carries
   `verifies: [B-N]`. An unverified behavior is a hole.
2. **Every eval maps to ≥1 behavior** — an eval with no `verifies:` is testing
   something the spec never promised (scope creep) and is rejected.

`validate-task-spec.sh` walks the `B-N` ⇄ `verifies:` graph in both directions and
hard-fails on any unmatched node. The deep dive is in [six-zones.md](six-zones.md).

> On the `lite` profile Behavior may collapse into the Goal; `standard`/`full`
> require it as its own zone. See [profiles.md](profiles.md).

---

## Zone 3 — Contract (The Moat)

This is the zone that differentiates Task-Spec from every other task format.

```markdown
## Success Criteria

Each criterion is a runnable bash function returning 0 (pass) or non-zero (fail).
Each MUST be terminal (deterministic, idempotent, non-flaky).

```bash
# eval-1 (verifies B-2): stack starts cleanly
eval_1() {
  docker compose -f docker/langfuse-compose.yml up -d
  sleep 30
  test "$(docker ps --filter 'name=anthive-langfuse' --filter 'health=healthy' | wc -l)" -ge 1
}

# eval-2 (verifies B-2): UI reachable
eval_2() {
  curl -fs http://localhost:3000/api/public/health | jq -e '.status == "OK"'
}

# eval-3 (verifies B-1): real trace lands with expected attrs
eval_3() {
  python scripts/langfuse_smoke.py
}

# eval-4 (verifies B-2): runbook produced
eval_4() {
  test -f docs/observability-runbook.md && \
    grep -qi "first-time setup" docs/observability-runbook.md
}
```

## Validation Card

```yaml
success_criteria:
  - id: eval_1
    description: Docker stack reaches healthy state
    runnable: bash
    terminal: true
    expected_duration_sec: 60
    verifies: [B-2]
  - id: eval_2
    description: Langfuse UI reachable
    runnable: bash
    terminal: true
    expected_duration_sec: 5
    verifies: [B-2]
  - id: eval_3
    description: Real OTEL trace lands with expected resource attributes
    runnable: bash
    terminal: true
    expected_duration_sec: 30
    verifies: [B-1]
  - id: eval_4
    description: Runbook documents repeatable procedure
    runnable: bash
    terminal: true
    expected_duration_sec: 1
    verifies: [B-2]

retry_policy:
  max_iterations: 15
  circuit_breaker_no_progress: 3
  on_terminal_failure: park_with_context

agent_contract:
  version: 2
  read: [intent, behavior, contract, guardrails, operations]
  produce: [docs/observability-runbook.md, docker/langfuse-compose.yml]
  required_tools: [bash, docker, curl, python]
  timeout_minutes: 20
  sandbox_type: host
  emit: [pass, fail, retry_with_reason, parked_with_context]
  backend_metadata: {}
```

## Exit Check

```bash
# Final proof-of-done. Run as a single command; returns 0 only when task is complete.
eval_1 && eval_2 && eval_3 && eval_4
```
```

### Contract field reference

| Field | Type | Required | Rule |
|-------|------|----------|------|
| `success_criteria` | bash functions | yes | At least 1, each must be terminal + idempotent |
| `validation_card.success_criteria` | YAML list | yes | One entry per bash function; descriptions in English; each carries `verifies: [B-N]` |
| `…[].verifies` | list[string] | yes | The `B-N` behaviors this eval proves; every eval maps to ≥1 behavior |
| `validation_card.retry_policy` | YAML object | yes | max_iterations, circuit_breaker, on_terminal_failure |
| `validation_card.agent_contract` | YAML object | yes | v2 schema: `version: 2`, `read`/`produce`/`emit` as lists, `required_tools`, `timeout_minutes`, `sandbox_type`, `backend_metadata` (see [agent-contract.md](agent-contract.md)) |
| `exit_check` | bash | yes | Single command combining all evals |

### Eval quality rules

1. **Terminal** — returns deterministically (no flaky network without retries)
2. **Idempotent** — running twice gives the same result
3. **Cheap before expensive** — order evals by cost; fail fast
4. **Explainable** — each eval has a one-line description WHY it exists
5. **Bash-portable** — no agent-specific tooling; standard POSIX where possible

---

## Zone 4 — Guardrails

```markdown
## Anti-Patterns

- **Don't [specific action]** — [reason]. [What to do instead].
- **Don't [specific action]** — [reason]. [What to do instead].

## Do-Not-Touch

Files the executor MUST NOT modify:

- `anthive/observability.py` — already implemented; this task verifies it
- `functions/adf/**` — auto-generated; will be regenerated by build-copy-src.sh
- `.env` — secrets layer; not the executor's concern
```

### Guardrail rules

| Rule | Why |
|------|-----|
| Anti-patterns must be SPECIFIC | "Be careful" is not a guardrail; "Don't edit auto-generated files" is |
| Do-not-touch lists EXACT paths | Globs allowed (`functions/adf/**`); vague descriptions rejected |
| Both sections are NON-OPTIONAL | If genuinely empty, write `(none)` — silence is rejected |

---

## Zone 5 — Operations

```markdown
## Open Questions

Things the executor should resolve DURING build, not assume:

1. **[Question]** — [why it matters, who to ask, fallback behavior]
2. **[Question]** — [why it matters]
```

Zone 5 admits unknowns up front. Honest tasks have open questions; dishonest
tasks pretend everything is known. On the `full` profile, an unresolved question
may be promoted to a first-class `blocked` hole (see [decomposition.md](decomposition.md)).

---

## Zone 6 — Reversal & Runtime (full profile)

Only required on the `full` profile. It answers two questions the other zones
leave open: how to undo the change, and how to see it working in production.

```markdown
## Rollback Plan

[One paragraph: how to undo this task if it ships broken — the exact revert
command, feature flag, or compensating action, plus the blast radius.]

## Observability Hooks

- **Metric/log/trace to add** — [what signal proves this is healthy in prod].
- **Alert/dashboard** — [where an operator sees it; threshold if any].
```

`lite` and `standard` profiles omit Zone 6; `full` rejects its absence. See
[profiles.md](profiles.md) for the per-profile zone matrix.

---

## Status Lifecycle

```text
    ┌─────────┐
    │  ready  │ ◄──────────────────┐
    └────┬────┘                    │
         │ executor claims         │ unblock
         ▼                         │
    ┌──────────────┐               │
    │ in-progress  │               │
    └──────┬───────┘               │
           │                       │
     ┌─────┴─────┬──────────┐      │
     ▼           ▼          ▼      │
  ┌──────┐  ┌────────┐  ┌────────┐ │
  │ done │  │ parked │  │blocked │─┘
  └──────┘  └────────┘  └────────┘
   evals     budget       waiting
   passed    exhausted    on dep
```

Status transitions are **atomic** — see `references/patterns/atomic-status-transitions.md`.

---

## Agent Contract (cross-vendor portability)

Any agent picking up a Task-Spec MUST honor this contract:

```yaml
on_pickup:
  - read: zones 1-6 in order (present-for-profile)
  - parse: validation_card YAML (incl. agent_contract v2 schema)
  - acquire: lock via state-management layer

per_iteration:
  - execute: implementation, writing only the declared produce: paths
  - run: all success_criteria as bash
  - emit: pass | fail | retry_with_reason
  - log: append to _metrics.jsonl

on_terminal_state:
  pass: transition status -> done; archive to tasks/done/
  budget_exhausted: transition status -> parked; archive to tasks/parked/
  unrecoverable_error: transition status -> blocked; do NOT archive
```

If an agent can't honor this contract, it can't consume Task-Spec. Period.

---

## File-system Conventions

```text
tasks/
├── T-20260519-foo.md           ← active backlog (status: ready | in-progress | blocked)
├── done/
│   └── T-20260518-bar.md       ← completed (status: done)
├── parked/
│   └── T-20260517-baz.md       ← budget-exhausted or blocked-with-context
├── _state.yaml                 ← derived index (REBUILDABLE from frontmatter)
└── _metrics.jsonl              ← append-only forensic ledger
```

State management rules in `references/concepts/backlog-architecture.md`.

---

## Versioning

Task-Spec follows semver, and the conformed version is **declared in the file**:

- **`format_version`** — v3 specs set `format_version: 3` in the frontmatter.
  Absent ⇒ 1 (legacy v0 ⇒ 0). The `profile` axis is orthogonal and defaults to
  `standard`.
- **v1 / v2 / v3** — each major bump may add breaking structure (v3 added the
  Behavior zone + traceability); older specs remain valid under their declared
  `format_version`, and `migrate-legacy-task.sh` upgrades v0 markdown.

`validate-task-spec.sh` reads `format_version`, selects the matching ruleset, and
reports the matched version on output.

---

## Compliance — When is a file a Task-Spec?

A markdown file is a valid Task-Spec v3.1 if and only if (zone requirements scale
with `profile` — see [profiles.md](profiles.md)):

- [ ] YAML frontmatter present with all REQUIRED fields
- [ ] `effort` is `S` or `M` (not `L`/`XL`)
- [ ] Intent has Goal (every profile) + Context (`standard`/`full`)
- [ ] Contract has ≥1 runnable bash success criterion
- [ ] Contract has validation_card YAML
- [ ] Contract has exit_check bash
- [ ] Behavior zone present on `standard`/`full`, and every `B-N` is verified by ≥1 eval whose `verifies:` references it (bidirectional traceability)
- [ ] Guardrails has Anti-Patterns + Do-Not-Touch (or explicit `(none)`) on `standard`/`full`
- [ ] Operations has Open Questions (or explicit `(none)`) on `standard`/`full`
- [ ] Rollback Plan + Observability Hooks present on `full`
- [ ] No leftover `{{PLACEHOLDER}}` strings
- [ ] `touches_paths` references real or planned files
- [ ] `source_note` references an existing file

`validate-task-spec.sh` enforces these rules; the structural sign-off envelope
and the Behavior↔eval traceability chain are part of the same check surface.

---

## What Task-Spec is NOT

To prevent scope creep, here's what Task-Spec **deliberately excludes**:

| Excluded | Why | Where it lives instead |
|----------|-----|------------------------|
| Priority ordering | Executor concern | taskship's scheduler / anthive's queue |
| Parallel dispatch logic | Executor concern | anthive |
| PR creation | Executor concern | taskship/anthive both emit draft PRs |
| OTEL trace IDs | Executor concern | Whatever observability the executor uses |
| Cost ceilings (`budget_usd`) | Executor concern | Whatever metering the executor applies |
| Cross-task dependencies as a DAG | Executor concern | `depends_on` declares the edges; `validate-task-spec.sh` does cycle detection (v3.1) |
| Multi-step plans within one task | Anti-pattern | Decompose into multiple Task-Specs |

Task-Spec is the FORMAT. Execution is someone else's job.

---

## Reference — A complete minimal example

```markdown
---
id: T-20260519-add-health-endpoint
title: Add /health endpoint to api server
status: ready
format_version: 3
profile: standard
effort: S
budget_iterations: 10
agent: any
depends_on: []
touches_paths:
  - src/api/server.py
  - tests/test_health.py
source_note: notes/2026-05-19-monitoring-followups.md
created: 2026-05-19T14:00:00-0300
tags: ["api", "monitoring"]
---

> **Why:** Load balancer health checks fail because there's no /health endpoint.

## Goal

Add a `/health` endpoint returning `{"status":"ok"}` with HTTP 200 to the api server.

## Context

The api server is FastAPI-based at `src/api/server.py`. No existing health
endpoint exists. The k8s probes documented in `infra/k8s/api.yaml` already
reference `/health` (currently 404).

## Behaviors

- **B-1** — GIVEN the api server is running
  WHEN a client GETs `/health`
  THEN it returns HTTP 200 with body `{"status":"ok"}`.

## Success Criteria

```bash
eval_1() {
  # eval-1 (verifies B-1): server starts cleanly
  uvicorn src.api.server:app --port 8001 &
  SERVER_PID=$!
  sleep 2
  test -d /proc/$SERVER_PID 2>/dev/null || ps -p $SERVER_PID > /dev/null
}

eval_2() {
  # eval-2 (verifies B-1): /health returns 200 with {"status":"ok"}
  curl -fs http://localhost:8001/health | jq -e '.status == "ok"'
}

eval_3() {
  # eval-3 (verifies B-1): test exists and passes
  pytest tests/test_health.py -q
}
```

## Validation Card

```yaml
success_criteria:
  - {id: eval_1, description: "Server starts cleanly", runnable: bash, terminal: true, verifies: [B-1]}
  - {id: eval_2, description: "/health returns 200 + correct JSON", runnable: bash, terminal: true, verifies: [B-1]}
  - {id: eval_3, description: "Test for /health passes", runnable: bash, terminal: true, verifies: [B-1]}

retry_policy:
  max_iterations: 10
  circuit_breaker_no_progress: 3
  on_terminal_failure: park_with_context

agent_contract:
  version: 2
  read: [intent, behavior, contract, guardrails, operations]
  produce: [src/api/server.py, tests/test_health.py]
  required_tools: [bash, uvicorn, curl, pytest]
  timeout_minutes: 10
  sandbox_type: host
  emit: [pass, fail, retry_with_reason]
  backend_metadata: {}
```

## Exit Check

```bash
eval_1 && eval_2 && eval_3 && kill $SERVER_PID 2>/dev/null; true
```

## Anti-Patterns

- **Don't add liveness/readiness logic** — this is the simplest possible health check; depth comes later.
- **Don't add auth** — health endpoints are public by k8s convention.

## Do-Not-Touch

- `infra/k8s/api.yaml` — already references the correct path; no change needed.

## Open Questions

(none — this task is fully specified)
```

That's a complete, valid Task-Spec (`format_version: 3`, `profile: standard`).
~90 lines. Any conformant engine can pick it up.

---

## Why this format won

Task-Spec won the design space because of one insight:

> **Specs that verify themselves don't need humans in the middle of the loop.**

Every other task format on the market is **readable** — humans interpret it,
agents interpret it, success is judged by humans interpreting outputs. Task-Spec
makes the success criteria **executable**. Now the spec carries its own
verification. The human only enters at intent (front) and PR review (back).

This is the same conceptual leap as:

- TDD (tests come first, code is judged by them)
- Infrastructure-as-code (config is executable, not described)
- Data contracts in DBT (data quality assertions ARE the spec)
- Type systems (types are checked, not asserted in prose)

Task-Spec is **Eval-Driven Development for agentic tasks** — the next step in
that lineage.

---

## Version History

| Version | What it added |
|---------|---------------|
| **v0** (legacy) | Pre-format tasks: markdown checklists, no runnable evals, effort L/XL allowed. Tolerated by the validator under the layered policy (warns, never hard-fails). Migrate via `migrate-legacy-task.sh`. |
| **v1** (2026-05-19) | Four zones (Intent / Contract / Guardrails / Operations), runnable bash evals, validation_card YAML, pipe-delimited `agent_contract`, frontmatter id/status/effort/budget/agent/touches_paths. |
| **v2** | Six zones (adds **Rollback Plan** + **Observability Hooks**); cross-vendor `agent_contract` schema (`produce` as list, `emit` enum, `required_tools`, `timeout_minutes`, `sandbox_type`, `backend_metadata`); accountability frontmatter (`owner`, `priority`, `severity`, `due_date`, `precondition`); severity-scaled quality thresholds; `creates_paths` for greenfield tasks. |
| **v2.2** | Key-optional HMAC sign-off envelope `signed_off_sig` (`hmac-sha256-v1:<keyid>:<hex>`), sealed by `safe-to-delegate.sh --stamp` and re-verified by `validate-task-spec.sh` across three tiers (Tier 1 keyed/verified, Tier 2 structural-only/supervised, Tier 3 mismatch/hard-fail). See [signed-off.md](signed-off.md). |
| **v3** | Effort-scaled **profiles** (`lite | standard | full`); the **Behavior** zone with bidirectional behavior↔eval traceability (`B-N` ⇄ eval `verifies:`); the POST-execution **accept-task gate** (`accept-task.sh` → `accepted: true`, with `accepted_by`/`accepted_at`); executor **conformance levels** (L0/L1/L2) mapped to A2A `TaskState`; one-level **decomposition** (`parent:` + flat index) with open questions as first-class `blocked` holes; `execution_backend` as an open string. |
| **v3.1** (current) | Acceptance-gate options `--gold-sanity` (Goodhart guard via `baseline_ref`/`reference_solution`) and `requires:` (sandbox isolation declaration); canonical A2A v1.0 `TaskState` mapping; `depends_on` DAG cycle detection; published JSON Schema (Draft 2020-12). |

The validator accepts every version via `format_version` (default 1 if absent,
0 = legacy). v3 specs declare `format_version: 3`; the `profile` axis is
orthogonal and defaults to `standard` when absent.

---

## See also

- [eval-driven-development.md](eval-driven-development.md) — the methodology
- [edd-vs-sdd-honest-comparison.md](edd-vs-sdd-honest-comparison.md) — when EDD wins, when SDD wins
- [six-zones.md](six-zones.md) — zone-by-zone deep dive (the canonical anatomy, incl. Behavior)
- [profiles.md](profiles.md) — `lite | standard | full` and the traceability rule
- [conformance-levels.md](conformance-levels.md) — L0/L1/L2 executor certification + A2A mapping
- [decomposition.md](decomposition.md) — turning FEATURE-altitude intent into gateable atoms
- [signed-off.md](signed-off.md) — the pre-dispatch gate and the `signed_off_sig` HMAC envelope
- [effort-gate.md](effort-gate.md) — S/M/L/XL rules
- [agent-contract.md](agent-contract.md) — cross-vendor contract details
- [backlog-architecture.md](backlog-architecture.md) — 5-layer state management
- [../patterns/runnable-bash-evals.md](../patterns/runnable-bash-evals.md) — eval writing patterns
- [../patterns/validation-card-yaml.md](../patterns/validation-card-yaml.md) — YAML contract patterns
