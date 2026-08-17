# ADR-0004: External Task-Spec contract boundary

- Status: accepted
- Date: 2026-08-15
- Supersedes: the embedded Task Pack portions of ADR-0001, ADR-0002, and ADR-0003

## Context

Seamwise 0.1 copied and wrapped a Task Pack implementation. That preserved
behavior during initial extraction, but it also duplicated Task-Spec code,
release state, validation, signing, and host skills. Task-Spec could not evolve
independently without a Seamwise vendor update.

The ecosystem responsibility split now requires Seamwise to own decomposition
and Task-Spec to own atomic execution contracts and their authority.

## Decision

Seamwise 0.2 removes the embedded engine, direct `task-spec` console script,
`seamwise tasks` authority surface, vendored Task-Spec skill, provenance
manifest, and parity suite.

Seamwise does not invoke Task-Spec. It emits reviewed `TaskPlan/v1` and
`SeamwiseTaskPlanLineage/v1` in one transaction, then stops. Converge or another
explicit composition caller negotiates the independent Task-Spec engine,
validates the TaskPlan, materializes tasks, and persists the cross-engine
receipt.

Seamwise validates its own topology and projection integrity only. The lineage
binds intent, review, delivery plan, canonical TaskPlan digest, and every unit's
seam, swimlane, and capability leg. Seamwise never imports Task-Spec code,
parses Task-Spec Markdown, or consumes Task-Spec authority.

## Consequences

Positive:

- each repository can release, upgrade, roll back, and test independently;
- Task-Spec remains the only task contract and authority implementation;
- composition inputs and lineage failures are explicit and machine-readable;
- the Seamwise wheel is materially smaller;
- callers can substitute a conformant Task-Spec release without changing
  Seamwise internals.

Tradeoffs:

- composed use requires a coordinator to negotiate both engines;
- the products intentionally share the small `TaskPlan/v1` contract;
- cross-engine end-to-end tests need independently built products.

## Invariant

> Seamwise decomposes. Task-Spec contracts. Converge coordinates.
