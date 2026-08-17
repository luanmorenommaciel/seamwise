# Decision 0003: Codex, Claude Code, and chat experience

- Status: accepted
- Date: 2026-08-03
- Updated: 2026-08-15

## Decision

Ship five focused Seamwise skills:

- `seamwise`
- `to-seam-map`
- `to-delivery-plan`
- `to-task-graph`
- `to-task-specs`

Installations are receipt-owned, hash-verified, non-clobbering, and reversible
for Codex and Claude Code. Chat hosts consume a bounded
`agent-context --host chat` packet.

The guided experience works one confirmed pass at a time, asks one concise
unanswered question, distinguishes proposals from verified artifacts, and
stops at human review.

## External Task-Spec

Seamwise no longer installs a direct Task-Spec skill or exposes Task-Spec
authority commands. The `to-task-specs` skill only guides the reviewed
TaskPlan and lineage projection, then hands both artifacts to the external
composition caller with `dispatch_authorized: false`.

Users install Task-Spec separately and use its own skill or CLI for
authorization, handoff, evaluation, and acceptance.

## Trust rule

Host prose is explanation, never authority. Only repository execution and
versioned machine receipts establish current state.
