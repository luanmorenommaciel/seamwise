# Decision 0002: Stable machine contracts

- Status: accepted
- Date: 2026-08-02
- Updated: 2026-08-15
- Contract version: 1

## Seamwise result envelope

Every command in JSON mode emits exactly one object with:

- `contract: SeamwiseCLIResult/v1`
- `engine_version`
- `schema_version`
- `command`
- `ok`
- `token`
- `exit_code`
- `workspace`
- `artifacts`
- `diagnostics`
- `next`
- optional `data`

Human rendering is derived from this object. Automation never parses Rich
terminal prose.

## Stable phase tokens

- `WORKSPACE=READY`
- `SEAM_MAP=READY`
- `SEAM_MAP=NEEDS_DISCOVERY`
- `SEAM_MAP=NEEDS_OWNER_INPUT`
- `SEAM_MAP=NEEDS_ARCHITECTURE_DECISION`
- `DELIVERY_PLAN=NEEDS_REVIEW`
- `DELIVERY_PLAN=READY`
- `TASK_GRAPH=READY`
- `TASK_GRAPH=CYCLE`
- `TASK_GRAPH=COLLISION`
- `TASK_GRAPH=UNPROVABLE_NODE`
- `STATUS=READY`
- `STATUS=BLOCKED`

## Composition contract

Task-Spec wrapper tokens formerly owned by Seamwise are removed. Seamwise
advertises `SeamwiseCapabilities/v1` and emits:

- `TaskPlan/v1`
- `SeamwiseTaskPlanLineage/v1`

It does not call or consume Task-Spec at runtime. The composition coordinator
negotiates both engines and owns the subprocess boundary.

See [Decision 0004](0004-external-taskspec-boundary.md).

## Failure behavior

Invalid author input, stale review receipts, unsafe paths, conflicting task
topology, partial output transactions, and projection drift all fail closed
with named diagnostics.
