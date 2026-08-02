---
id: T-20260721-ex-xxl-analytical-backbone
title: "XXL example — the analytical backbone (top decomposition node)"
status: ready
format_version: 3
profile: lite
effort: XXL
budget_iterations: 15
agent: any
depends_on: []
touches_paths: []
children:
  - T-20260721-xl-swimlane-capture
  - T-20260721-ex-xl-swimlane-transform
  - T-20260721-xl-swimlane-serve
source_note: "effort-gate v3.4 worked example (XXL node) — the whole backbone"
created: 2026-07-21T00:00:00Z
execution_backend: any
---

# XXL example — the analytical backbone (top decomposition node)

> **Why XXL:** the entire capture → transform → serve backbone. It could never fit one
> context window or verify as one PR. It decomposes into three XL swimlane nodes, each of
> which decomposes into leaf atoms — a tree, tasks all the way down. This is the dark
> factory's root: the node composes its swimlanes' results into the working system.

## Goal
Stand up the analytical backbone by completing its three swimlane nodes (capture,
transform, serve), each itself a decomposition into leg atoms. The root owns no work
directly — it is the composition point where the verified slices become the system.

## Success Criteria
```bash
eval_1() { for c in T-20260721-xl-swimlane-capture T-20260721-ex-xl-swimlane-transform T-20260721-xl-swimlane-serve; do grep -q '^status: done' "tasks/$c.md" || return 1; done; }
```

## Validation Card
```yaml
success_criteria:
  - id: eval_1
    description: every child swimlane node is accepted (done)
    runnable: bash
    check_type: deterministic
    terminal: true
    expected_duration_sec: 5
retry_policy:
  max_iterations: 15
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
