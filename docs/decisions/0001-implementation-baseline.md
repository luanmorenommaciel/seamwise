# Decision 0001: Implementation baseline

- Status: accepted
- Date: 2026-08-02
- Updated: 2026-08-15

## Decision

Implement Seamwise as a Python 3.11+ CLI with deterministic transformations,
versioned JSON Schemas, SQLite-free repository artifacts, explicit file locks,
atomic writes, and a stable JSON result envelope.

Preserve the canonical semantic chain:

```text
Delivery Intent → seam → swimlane → capability leg → atomic task contract
```

One seam has one owning swimlane. Capability legs describe observable states,
not activities. Task topology must prove dependencies, contentions, and
independent done conditions.

## Historical extraction

Version 0.1 used an embedded Task Pack as a move-first extraction technique.
That implementation detail is superseded by
[Decision 0004](0004-external-taskspec-boundary.md). The current architecture
retains the semantic chain while emitting a reviewed TaskPlan for an external
coordinator to pass to the independent Task-Spec product.

## Evidence rule

The canonical PDF describes the target architecture. Current shipped behavior
is established by executable code, schemas, tests, built packages, and release
evidence.
