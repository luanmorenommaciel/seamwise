---
name: to-task-specs
description: Project a reviewed Seamwise delivery plan into TaskPlan/v1 and digest-bound lineage without materializing tasks. Use when asked to compile a ready Seamwise graph or inspect its external Task-Spec boundary.
---

# To Task Specs

Use Seamwise only for reviewed projection. Never recreate Seamwise, Task-Spec,
or coordinator behavior in the model.

## Workflow

1. Run `seamwise --workspace "<path>" --json doctor --host core` and
   `seamwise --workspace "<path>" --json capabilities`.
2. Run `seamwise --workspace "<path>" --json status`. Stop unless the delivery
   plan has a current digest-bound review.
3. Run `seamwise --workspace "<path>" --json compile` once. It writes exactly
   `seamwise/task-plan.json` and `seamwise/task-plan-lineage.json`.
4. Confirm `TASK_GRAPH=READY`, `TaskPlan/v1`,
   `SeamwiseTaskPlanLineage/v1`, and `dispatch_authorized: false`.
5. Run Seamwise status again and report the exact artifact paths, unit count,
   TaskPlan digest, and integrity diagnostics.
6. Stop. TaskPlan validation, materialization, authorization, handoff,
   evaluation, and acceptance require Task-Spec plus an explicit composition
   caller. They are not Seamwise operations.

## Trust boundary

- Consume only `SeamwiseCLIResult/v1` and the two digest-bound artifacts.
- Do not invoke or parse Task-Spec from this skill.
- Do not modify either projection to make Seamwise status green.
- Treat partial, changed, stale, or unowned projection outputs as a closed gate.
- Successful Seamwise compilation still reports `dispatch_authorized: false`.
