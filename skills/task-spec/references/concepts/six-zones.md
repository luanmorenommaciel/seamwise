# The Six Zones

> **Purpose**: Anatomy of a Task-Spec v3 file. Each zone has a specific job.
> **Confidence**: HIGH
> **MCP Validated**: 2026-05-19

A Task-Spec is YAML frontmatter + the six-zone model. The irreducible core —
Intent's Goal, Contract's runnable Success Criteria, and the Exit Check — is
present at **every** profile; the remaining zones are required as the `profile`
escalates (see [profiles.md](profiles.md)). Two zones below — **Rollback** and
**Observability** — are required only on the `full` profile.

```text
┌─ YAML FRONTMATTER ─────────────────────────────────────────────┐
│ Machine-parseable metadata (required + optional fields)         │
├─ ZONE 1 — INTENT (why) ────────────────────────────────────────┤
│ Goal + Context. Lean. ≤100 lines.                              │
├─ ZONE 2 — CONTRACT (what + how to verify) ─────────────────────┤
│ Success Criteria + Validation Card + Exit Check                │
│ THE MOAT. The reason Task-Spec exists.                         │
├─ ZONE 3 — ROLLBACK (how to reverse) ───────────────────────────┤
│ Revert procedure if execution fails mid-task                   │
├─ ZONE 4 — OBSERVABILITY (what to watch) ───────────────────────┤
│ Expected duration, key metrics, alert conditions               │
├─ ZONE 5 — GUARDRAILS (what NOT to do) ─────────────────────────┤
│ Anti-Patterns + Do-Not-Touch list                              │
├─ ZONE 6 — OPERATIONS (admissions + recovery) ──────────────────┤
│ Open Questions                                                 │
└────────────────────────────────────────────────────────────────┘
```

## Zone 1 — Intent

**Job**: Tell the agent WHY this task exists, briefly.

**Contents**:
- One-line `> **Why:**` callout
- `## Goal` — concrete success in one paragraph
- `## Context` — lean background, link to existing docs

**Anti-pattern**: verbose context dumps. Zone 1 longer than Zone 2 = wrote a PRD instead of a Task-Spec.

**Rule**: ≤100 lines for Context. Link to existing docs instead of duplicating.

## Zone 2 — Behavior

**Job**: State, in plain language, what the task must DO — before any eval.

**Contents**:
- `## Behavior` — one or more `B-N` clauses in Given/When/Then form:
  `B-1: Given <precondition>, When <action>, Then <observable outcome>.`
- Each `B-N` is the unit of intent an eval proves.

**Traceability (the load-bearing rule)**: on `standard`/`full` every `B-N` MUST
be verified by ≥1 success criterion, and every eval's `verifies: [B-N]` MUST
reference a declared behavior. This bidirectional chain (intent → behavior →
eval) is what makes the spec machine-checked rather than sections stapled
together — see [profiles.md](profiles.md). On `lite`, behavior is implied by the
evals and this zone may be omitted.

**Rule**: no orphan behaviors (a `B-N` no eval covers) and no orphan evals (a
`verifies:` pointing at a non-existent `B-N`). The validator flags both.

## Zone 3 — Contract (THE MOAT)

**Job**: Define success mechanically. The agent's instruction set.

**Contents**:
- `## Success Criteria` — runnable bash evals (≥3, terminal, idempotent), each carrying `verifies: [B-N]`
- `## Validation Card` — YAML mirror of the evals + retry policy + agent contract
- `## Exit Check` — combined bash one-liner

**Why this is the moat**: Every other task format in the world is *readable*.
Zone 2 makes the success criteria *executable*. Now the spec carries its own
verification. Without Zone 2, this isn't Task-Spec.

**Rule**: At least 3 evals. Ordered cheap-to-expensive. Each terminal + idempotent.

## Zone 4 — Guardrails

**Job**: Bound the agent's scope.

**Contents**:
- `## Anti-Patterns` — specific "don'ts" with reasons
- `## Do-Not-Touch` — exact paths the agent must not modify

**Anti-pattern**: vague guidance ("be careful"). Anti-patterns must be SPECIFIC actions.

**Rule**: If genuinely empty, write `(none)` — silence is rejected by validation.

## Zone 5 — Operations

**Job**: Admit what's unknown; document recovery.

**Contents**:
- `## Open Questions` — things to resolve during build (not at authoring time).
  An unresolved question is a first-class blocker: it sets `status: blocked`
  (A2A `input-required`), not a footnote (see [decomposition.md](decomposition.md)).

**Why this matters**: Honest tasks have unknowns. Dishonest tasks pretend
everything is known. Zone 5 surfaces ambiguity instead of hiding it.

## Zone 6 — Rollback + Observability (full profile only)

**Job**: Make reversal and runtime expectations explicit for anything dispatched
unattended or carrying `security`/`financial-critical` severity.

**Contents**:
- `## Rollback Plan` — specific steps (git revert, file restore, state reset) to
  restore pre-task state, or `(none — additive with no destructive changes)`.
- `## Observability Hooks` — expected duration, key metrics, alert conditions,
  log tails, or `(none — no runtime observability required)`.

**Why this matters**: an unattended executor needs an explicit recovery path and
an explicit "this ran too long" signal. Required on `full`; on `lite`/`standard`
these may be omitted ([profiles.md](profiles.md)).

**Rule**: on `full`, if genuinely empty write `(none — …)` — silence is rejected.

## Zone interactions

| Zone | Reads from | Influences |
|------|------------|-----------|
| 1 (Intent) | User input | Behavior + every downstream zone's framing |
| 2 (Behavior) | Intent | The evals (each `B-N` demands ≥1 eval) |
| 3 (Contract) | Behavior + MCP research | Agent's execution loop |
| 4 (Guardrails) | MCP research + repo scan | Agent's blast radius |
| 5 (Operations) | Honest uncertainty | Where to ask human if loop stalls |
| 6 (Rollback + Observability) | Contract + blast radius + runtime surface | Recovery protocol + alert thresholds (full only) |

Zone 3 does the heavy lifting; Behavior (Zone 2) makes its evals traceable.
Zones 1, 4, 5, 6 are scaffolding that bounds, contextualizes, and
operationalizes the Contract.

## Frontmatter accountability

The YAML frontmatter carries machine-parseable metadata:

| Field | Required | Description |
|-------|----------|-------------|
| `id` | yes | T-YYYYMMDD-<kebab-slug> |
| `title` | yes | Human-readable task name |
| `status` | yes | ready \| in-progress \| blocked \| done \| parked |
| `effort` | yes | XS/S/M/L leaf · XL/XXL node (needs `children:`) |
| `budget_iterations` | yes | Max retry iterations |
| `agent` | yes | Agent hint (any, python-developer, etc.) |
| `depends_on` | yes | List of blocking task IDs |
| `touches_paths` | yes | Files or globs the task modifies |
| `source_note` | yes | Provenance (audit, meeting, ticket) |
| `created` | yes | ISO-8601 timestamp |
| `tags` | yes | Taxonomy labels |
| `owner` | no | Accountable individual |
| `priority` | no | P0 (drop everything) → P4 (backlog) |
| `severity` | no | cosmetic \| refactor \| feature \| bugfix \| security \| financial-critical |
| `due_date` | no | YYYY-MM-DD |
| `precondition` | no | What must be true before starting |

Priority and severity are orthogonal:
- **Priority** describes urgency (P0 = now, P4 = someday)
- **Severity** describes consequence (financial-critical = high stakes regardless of urgency)

A P3 financial-critical task exists (low urgency, high stakes).
A P0 cosmetic task exists (high urgency, low stakes).

## Related

- [task-spec-v1.md](task-spec-v1.md) — full format spec with zone examples
- [profiles.md](profiles.md) — which zones each profile requires + the traceability rule
- [eval-driven-development.md](eval-driven-development.md) — why the Contract zone is the moat
- [decomposition.md](decomposition.md) — open questions as first-class `blocked` holes
- [../patterns/runnable-bash-evals.md](../patterns/runnable-bash-evals.md) — Contract-zone eval writing
