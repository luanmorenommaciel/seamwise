# Decision 0002: Stable machine contracts

- Status: accepted
- Date: 2026-08-02
- Contract version: 1

## Result envelope

Every command supports `--json`. JSON mode writes exactly one envelope to
standard output:

```json
{
  "schema_version": 1,
  "command": "map",
  "ok": true,
  "token": "SEAM_MAP=READY",
  "exit_code": 0,
  "workspace": "/absolute/path",
  "artifacts": [],
  "diagnostics": [],
  "next": []
}
```

Human mode ends with the same token. Diagnostics go to standard error when they
would invalidate JSON output.

## Exit codes

| Code | Meaning |
| ---: | --- |
| 0 | Requested gate is ready or read-only query succeeded |
| 2 | Named evidence, owner input, architecture decision, or review resolution is required |
| 3 | Input or canonical artifact is invalid |
| 4 | Hash, lineage, tamper, cycle, or contention conflict prevents progress |
| 5 | Required provider, host, or external executable is unavailable |
| 10 | Internal mechanism error |

## Gate tokens

The Seam Map and Task Graph tokens are copied exactly from the blueprint. The
following version-1 Delivery Plan tokens fill the blueprint's unspecified
machine surface:

- `DELIVERY_PLAN=READY`
- `DELIVERY_PLAN=NEEDS_REVIEW`
- `DELIVERY_PLAN=OPEN_OBJECTIONS`
- `DELIVERY_PLAN=NEEDS_OWNER_INPUT`
- `DELIVERY_PLAN=NEEDS_ARCHITECTURE_DECISION`
- `DELIVERY_PLAN=ERROR`

The version-1 Task-Spec wrapper tokens are:

- `TASK_SPECS=EMITTED`
- `TASK_SPECS=VALID`
- `TASK_SPECS=PREFLIGHT_READY`
- `TASK_SPECS=SEALED`
- `TASK_SPECS=INVALID`
- `TASK_SPECS=ERROR`

Underlying Task Pack tokens remain byte-preserved and are included in envelope
diagnostics rather than replaced.

## Workspace resolution

Resolution order is explicit `--workspace`, `SEAMWISE_WORKSPACE`, nearest
ancestor containing `seamwise/intent.md`, Git root, then current directory.
Mutations are atomic, receipt-owned, and protected by a workspace lock. Dry-run
performs all reads and validations but writes no canonical, derived, receipt, or
telemetry file.
