---
id: T-20260721-ex-l-capture-steelthread
title: "L example — the capture steel thread, end-to-end (one coherent goal)"
status: ready
format_version: 3
profile: lite
effort: L
budget_iterations: 15
agent: any
depends_on: []
touches_paths: []
creates_paths:
  - cvg/capture/principal.sql
  - cvg/capture/pipelines/orders.py
  - cvg/capture/probe_commit_to_answer.py
  - cvg/capture/tests/test_steelthread.py
source_note: "effort-gate v3.4 worked example (L leaf, glm) — capture leg-01 steel thread"
created: 2026-07-21T00:00:00Z
execution_backend: glm
---

# L example — the capture steel thread, end-to-end (one coherent goal)

> **Why L (glm):** a single coherent done-condition — "a fresh source commit reaches a
> served answer" — but it spans provision → land → probe as ONE goal a long-horizon
> builder holds. It is the ceiling: if it needed several independent evals, it would be
> multiple M atoms. Accepted ONLY with execution_backend: glm.

## Goal
Prove the thin vertical slice: provision the read-only capture principal, land
`raw.orders` off the Postgres WAL via dlt, and a probe that inserts a source order and
asserts it surfaces through the backbone — the whole thread verified by ONE end-to-end
done-condition.

## Success Criteria
```bash
eval_1() { python cvg/capture/probe_commit_to_answer.py --assert-fresh-commit-visible; }
```

## Validation Card
```yaml
success_criteria:
  - id: eval_1
    description: a fresh source commit is visible end-to-end (the single coherent done-condition)
    runnable: bash
    check_type: deterministic
    terminal: true
    expected_duration_sec: 60
retry_policy:
  max_iterations: 15
  circuit_breaker_no_progress: 3
  on_terminal_failure: park_with_context
agent_contract:
  version: 2
  read: [intent, contract, guardrails, operations]
  produce: [code, test]
  required_tools: [bash, python, docker]
  timeout_minutes: 90
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
