---
name: to-delivery-plan
description: Transform an accepted Seamwise seam map into owning swimlanes, observable capability legs, a steel thread, dependencies, contention, and review objections through the shared CLI. Use when asked to form, challenge, validate, or revise a Seamwise delivery plan.
---

# To Delivery Plan

Use the shared CLI; keep planning proposals separate from validated artifacts and human decisions.

## Workflow

1. Run `seamwise --workspace "<path>" --json status`. Stop unless the seam map is ready and any required human acceptance is recorded.
2. Draft or refine only CLI-supported planning inputs. Keep every model-authored lane, leg, dependency, and objection labeled `proposed` until validation.
3. Run `seamwise --workspace "<path>" --json plan`.
4. A model may raise or analyze objections, but it may not resolve them on behalf of an owner. Only after an explicit human acceptance, record it with `seamwise --workspace "<path>" --json review --accept --reviewer "<human>" --reason "<reason>"`.
5. Accept plan readiness only when exit code is `0`, `ok` is `true`, and the token is exactly `DELIVERY_PLAN=READY`.
6. Otherwise preserve the gate: report the exact token, open objections, diagnostics, and `next` actions.

Enforce one owning swimlane per accepted seam. Name each capability leg as an observable capability state. Preserve the steel thread, explicit dependencies, and shared-resource contention; sibling tasks are not automatically parallel. Every objection must remain `OPEN`, or be explicitly `FIXED` or `ACCEPTED` with owner and rationale. CLI validation is not implementation evidence or human approval.
