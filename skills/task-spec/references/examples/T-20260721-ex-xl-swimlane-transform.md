---
id: T-20260721-ex-xl-swimlane-transform
title: "XL example — the transform swimlane (decomposition node)"
status: ready
format_version: 3
profile: lite
effort: XL
budget_iterations: 12
agent: any
depends_on: []
touches_paths: []
parent: T-20260721-ex-xxl-analytical-backbone
children:
  - T-20260721-ex-m-silver-dedup
  - T-20260721-tf-leg-02-gold
  - T-20260721-tf-leg-03-ducklake
source_note: "effort-gate v3.4 worked example (XL node) — transform swimlane"
created: 2026-07-21T00:00:00Z
execution_backend: any
---

# XL example — the transform swimlane (decomposition node)

> **Why XL:** a whole swimlane crosses layers (silver → gold → publish) and needs several
> independent test-suites — too big for one context window. It is NOT run directly: it
> DECOMPOSES into leaf task-specs (its legs). A worker dispatches the children and
> composes their results. No route out to SDD — tasks decompose into tasks.

## Goal
Deliver the transform lane (`raw.* → gold.*`) by completing its three leg atoms: silver
dedup (M), gold revenue model (M), and the DuckLake publish (M). This node owns no write
surface — its children do.

## Success Criteria
```bash
eval_1() { for c in T-20260721-ex-m-silver-dedup T-20260721-tf-leg-02-gold T-20260721-tf-leg-03-ducklake; do grep -q '^status: done' "tasks/$c.md" || return 1; done; }
```

## Validation Card
```yaml
success_criteria:
  - id: eval_1
    description: every child leg task-spec is accepted (done)
    runnable: bash
    check_type: deterministic
    terminal: true
    expected_duration_sec: 5
retry_policy:
  max_iterations: 12
  circuit_breaker_no_progress: 3
  on_terminal_failure: park_with_context
agent_contract:
  version: 2
  read: [intent, contract]
  produce: [docs]
  required_tools: [bash]
  timeout_minutes: 10
  sandbox_type: host
  output_artifacts: []
  mcp_dependencies: []
  emit: [pass, fail]
  backend_metadata: {}
```

## Exit Check
```bash
eval_1
```
