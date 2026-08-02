# Runbook: Decomposing Intent into Atomic Task-Specs

> **Use when:** you have a fuzzy intent, a PRD/design, or "a set of calls" that is
> too big for one atomic spec, and you need N linked Task-Specs that each pass the
> safe-to-delegate gate on their own. This is the *fan-out* runbook; once the atoms
> exist, [batch-sprint-compose.md](./batch-sprint-compose.md) is how you generate
> their stub files fast.

## Why decompose

One spec must be atomic — S/M effort, one blast radius, evals that prove *one*
unit of work. A PRD or a multi-step intent is none of those. Decomposition turns
the big thing into a flat set of atoms plus the edges between them, so each atom
can be authored, gated, and dispatched independently. See
[references/concepts/decomposition.md](../references/concepts/decomposition.md)
for the concept and the index+detail shape.

## Inputs

- A parent artifact: a PRD, a design doc, a meeting note, or a paragraph of intent
- (optional) a known target codebase, if the atoms touch in-repo paths

## The method (two-layer: index + detail)

The converged shape is **a flat parent index of stubs + per-task detail specs** —
not a deep tree. The index is human-skimmable; each detail spec is a real,
gateable Task-Spec.

### Step 1 — Spawn `task-architect` to find the atoms

Hand the parent artifact to the **`task-architect`** agent (Phase 4 of the main
workflow). Ask it for the *decomposition*, not the specs: a list of atoms, each
with a slug, one-line description, the `depends_on` edges, and — critically — any
**open questions / holes** it could not resolve from the artifact alone.

The agent applies the Agreement Matrix and returns one row per atom:

```text
slug                  depends_on        hole?
extract-otel-config   []                (none)
wire-collector        [extract-otel-config]   which exporter endpoint? (BLOCKER)
verify-trace-lands    [wire-collector]  (none)
```

### Step 2 — Write the parent index

Create one flat index listing every atom as a stub. The index is a map, not a
spec — it carries slug, title, `depends_on`, and hole status only:

```markdown
# Decomposition: <parent title>
parent: docs/prd/observability.md

| atom | depends_on | hole | status |
|------|-----------|------|--------|
| T-YYYYMMDD-extract-otel-config | — | — | ready |
| T-YYYYMMDD-wire-collector | extract-otel-config | endpoint unknown | **blocked** |
| T-YYYYMMDD-verify-trace-lands | wire-collector | — | ready |
```

### Step 3 — Generate the detail stubs

Feed the atom slugs to `batch-generate.sh` (do NOT re-implement it). One line per
atom in `slug: description` form, then:

```bash
bash ~/.claude/skills/task-spec/scripts/batch-generate.sh \
    --intent-file atoms.txt \
    --effort S \
    --source-note docs/prd/observability.md \
    --queue
```

### Step 4 — Wire the edges and the parent

In each generated detail spec, fill two frontmatter fields that turn the flat
list into a graph:

- **`parent:`** — the path/url of the index or the source PRD. The detail spec
  DISTILLS the parent; it never copies it. The validator resolves repo-relative
  `parent:` paths.
- **`depends_on:`** — the slugs of atoms that must finish first. The validator
  confirms every `depends_on` references an existing task.

### Step 5 — Mark the holes (first-class blockers)

An unresolved open question is **not** a footnote — it is a blocker that makes the
atom NOT safe-to-delegate. Encode every hole two ways:

1. **Machine-readable:** set `status: blocked` and fill `blocked_reason:` with the
   hole. The validator maps `blocked` → A2A `input-required` via `ts_a2a_state()`
   in `_lib.sh` — so an A2A-aware dispatcher sees the atom is waiting on input,
   not ready to run.
2. **Human-readable:** write the question in the `## Open Questions` zone (keep it
   non-`(none)`). That is the prose a human resolves before unblocking.

A `blocked` atom is not `ready`, so a backlog picker (`list-ready.sh`) will not
hand it to an executor. When the hole is answered, transition it:

```bash
bash ~/.claude/skills/task-spec/scripts/transition-status.sh \
    T-YYYYMMDD-wire-collector ready "endpoint confirmed: /api/public/otel/v1/traces"
```

Only then does the atom become eligible for the safe-to-delegate gate.

### Step 6 — Gate each atom independently

Each detail spec runs the normal pre-gate. A `ready` atom with no holes:

```bash
bash ~/.claude/skills/task-spec/scripts/safe-to-delegate.sh --stamp \
    tasks/queue/T-YYYYMMDD-extract-otel-config.md
```

A `blocked` atom is intentionally NOT gated — its hole is unresolved. Leaving it
`blocked` is the correct, honest state. The gate (`safe-to-delegate.sh`) remains
the only path to `signed_off: true`; decomposition does not bypass it.

## Expressing a hole the validator already surfaces

No new script behavior is required. The hole convention reuses existing fields:

| Field | Value for an open hole | Effect |
|-------|------------------------|--------|
| `status:` | `blocked` | validator maps → A2A `input-required`; not `ready`, so not picked up |
| `blocked_reason:` | the one-line question | machine-readable blocker reason |
| `## Open Questions` | non-`(none)` prose | human-readable hole to resolve |
| `depends_on:` | upstream atom slugs | validator confirms edges resolve |
| `parent:` | PRD/index path | validator confirms the link resolves |

A reviewer verifies the convention held by running the validator and reading the
A2A line it prints:

```bash
# A holed atom must report A2A: input-required (NOT submitted/ready):
bash ~/.claude/skills/task-spec/scripts/validate-task-spec.sh \
    tasks/queue/T-YYYYMMDD-wire-collector.md | grep 'A2A: input-required'

# And it must NOT appear in the ready list:
bash ~/.claude/skills/task-spec/scripts/list-ready.sh | grep -q wire-collector \
    && echo "BUG: holed atom is delegate-eligible" || echo "OK: holed atom withheld"
```

## Anti-patterns

- **Don't build a deep tree.** The shape is flat index + detail atoms, not
  sub-tasks of sub-tasks. Deep nesting hides the `depends_on` graph.
- **Don't bury a blocker in prose only.** An `## Open Questions` note with
  `status: ready` is a lie to the gate — the atom looks delegate-safe but isn't.
  Always pair the prose with `status: blocked`.
- **Don't copy the PRD into each atom.** Reference it via `parent:`; Zone 1
  carries only the one-paragraph distillation needed to execute the atom.
- **Don't re-implement batch generation.** `batch-generate.sh` already makes the
  stubs; this runbook only adds the index, the edges, and the holes.

## Remember

> **"Decomposition makes the graph explicit and the holes honest: each atom picks
> its own profile, declares its edges, and refuses to be delegated while a
> question is still open."**
