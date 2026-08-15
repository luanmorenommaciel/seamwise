---
name: to-task-graph
description: Compile a reviewed Seamwise delivery plan into a dependency-safe, lineage-complete Task-Spec graph through the shared CLI. Use when asked to decompose capability legs, inspect critical path or concurrency, detect cycles or write-surface collisions, or validate an atomic task graph.
---

# To Task Graph

Let the shared compiler own decomposition, lineage, and gate tokens.

## Workflow

1. Run `seamwise --workspace "<path>" --json status`. Stop unless the delivery plan is ready and its required review receipt is current.
2. Run `seamwise --workspace "<path>" --json compile`.
3. Accept graph readiness only when exit code is `0`, `ok` is `true`, and the returned graph token is exactly `TASK_GRAPH=READY`.
4. Run `seamwise --workspace "<path>" --json graph` to inspect the derived DAG and critical path without changing canonical inputs.
5. Otherwise report the exact cycle, collision, unprovable node, blocked dependency, stale lineage, or diagnostic returned by the CLI. Do not repair it by relabeling or deleting evidence.

Require each runnable leaf to own one coherent, independently provable done-condition. Justify concurrency with dependencies and contention rather than sibling position. Preserve lineage from Delivery Intent through seam, swimlane, and capability leg to each TaskPlan unit. Compilation emits no Task-Spec drafts; graph readiness is not materialization, execution, or implementation proof.
