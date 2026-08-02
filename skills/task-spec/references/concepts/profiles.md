# Concept: Effort-Scaled Profiles (v3)

> **Status:** normative (v3)
> **Field:** `profile: lite | standard | full`
> **Default when absent:** `standard` (every pre-v3 spec stays valid)

## Why profiles exist

The format's weight must scale with a task's consequence. A one-line doc fix and
a money-field parser change should not carry the same ceremony. Before v3 the
format was all-or-nothing, and the symptom was concrete: the format's own author
reached for a lighter shape when authoring real backlog tasks. Profiles fix the
weight problem **without** weakening the moat (runnable evals + the gate stay
mandatory at every level).

The `profile` axis is **orthogonal** to `format_version`. A v3 spec with no
`profile:` field is treated as `standard`, so nothing historical breaks.

## The three profiles

| Profile | Required zones | Traceability enforced? | Use when |
|---------|----------------|------------------------|----------|
| **lite** | Goal, Success Criteria, Validation Card, Exit Check | No | S effort, low blast radius; behavior is implied by the evals |
| **standard** | lite + **Behavior**, Context, Anti-Patterns, Do-Not-Touch, Open Questions | **Yes** (behavior ↔ eval) | The default; most M tasks and any task another person will read |
| **full** | standard + **Rollback Plan**, **Observability Hooks** | **Yes** | Anything dispatched **unattended**; severity `security`/`financial-critical`; reversal + runtime expectations must be explicit |

The irreducible core — present at **every** profile — is **Goal + runnable
Success Criteria + Exit Check**. That is the self-verifying unit; a profile only
changes how much *surrounding* context and guardrail the spec must carry.

## What the validator enforces

- `profile` must be one of `lite|standard|full` (absent → `standard`).
- **lite**: omitting Behavior/Context/Guardrails/Operations is allowed.
- **standard/full**: those zones are required; the **behavior ↔ eval traceability
  chain** is enforced (see [traceability](#traceability-the-load-bearing-rule)).
- **full**: Rollback Plan and Observability Hooks are required (a literal
  `(none — additive)` body is acceptable only when genuinely not applicable).

## Choosing a profile

Prefer the **lightest** profile that fits — rigor you don't need is friction that
suppresses adoption. Escalate when any of these is true:

- the change is hard to reverse → at least `full` (you owe a Rollback Plan)
- `severity` is `security` or `financial-critical` → `full`
- it will run unattended (overnight builder, cron, blind crank) → `full`
- another engineer must understand *why* and *what behavior* → `standard`

## Traceability: the load-bearing rule

For `standard`/`full`, every behavior `B-N` must be verified by ≥1 eval, and every
eval's `verifies:` must reference a declared behavior. This bidirectional coverage
is what elevates the format from "sections stapled together" to a machine-checked
chain (intent → behavior → eval). See [six-zones.md](six-zones.md) for the
Behavior zone anatomy and [eval-driven-development.md](eval-driven-development.md)
for why the eval is the moat.
