---
id: T-20260721-ex-m-silver-dedup
title: "M example — silver dedup-to-max-_lsn model + uniqueness check"
status: ready
format_version: 3
profile: lite
effort: M
budget_iterations: 12
agent: any
depends_on: []
touches_paths: []
creates_paths:
  - cvg/transform/models/silver/orders.sql
  - cvg/transform/models/silver/schema.yml
  - cvg/transform/tests/unique_business_key.sql
source_note: "effort-gate v3.4 worked example (M leaf) — transform leg-01 unit"
created: 2026-07-21T00:00:00Z
execution_backend: kimi
---

# M example — silver dedup-to-max-_lsn model + uniqueness check

> **Why M:** module-level, three coordinated files, one conceptual responsibility
> (deterministic dedup). Cites the sharpened seam contract so it can't drift.

## Goal
Build the silver `orders` model that dedups `raw.orders` to ONE row per business key by
keeping the **max-`_lsn`** change event (a `_op=delete` tombstone removes the key), plus a
dbt uniqueness test on the business key. Per the capture `raw.*` contract.

## Success Criteria
```bash
eval_1() { grep -qiE 'max\(_lsn\)|qualify.*row_number|_lsn desc' cvg/transform/models/silver/orders.sql; }
eval_2() { grep -q 'unique' cvg/transform/tests/unique_business_key.sql; }
eval_3() { grep -q 'orders' cvg/transform/models/silver/schema.yml; }
```

## Validation Card
```yaml
success_criteria:
  - id: eval_1
    description: model dedups by max-_lsn per key
    runnable: bash
    check_type: deterministic
    terminal: false
    expected_duration_sec: 2
  - id: eval_2
    description: a uniqueness test guards the business key
    runnable: bash
    check_type: deterministic
    terminal: false
    expected_duration_sec: 2
  - id: eval_3
    description: schema documents the model
    runnable: bash
    check_type: deterministic
    terminal: true
    expected_duration_sec: 2
retry_policy:
  max_iterations: 12
  circuit_breaker_no_progress: 3
  on_terminal_failure: park_with_context
agent_contract:
  version: 2
  read: [intent, contract, guardrails]
  produce: [code, test]
  required_tools: [bash]
  timeout_minutes: 20
  sandbox_type: host
  output_artifacts: []
  mcp_dependencies: []
  emit: [pass, fail]
  backend_metadata: {}
```

## Exit Check
```bash
eval_1 && eval_2 && eval_3
```
