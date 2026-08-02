---
id: T-20260721-ex-s-health-endpoint
title: "S example — add a /health endpoint to the serve API"
status: ready
format_version: 3
profile: lite
effort: S
budget_iterations: 8
agent: any
depends_on: []
touches_paths: []
creates_paths:
  - cvg/serve/api/health.py
  - cvg/serve/api/tests/test_health.py
source_note: "effort-gate v3.4 worked example (S leaf)"
created: 2026-07-21T00:00:00Z
execution_backend: kimi
---

# S example — add a /health endpoint to the serve API

> **Why S:** one coherent change across two tightly-coupled files (impl + its test),
> a couple files to read, one test-suite verifies it. Fits one context window.

## Goal
Add a `GET /health` route to the serve FastAPI that returns `{"status":"ok"}` (200), with
a unit test.

## Success Criteria
```bash
eval_1() { python -c "import ast,sys; ast.parse(open('cvg/serve/api/health.py').read())"; }
eval_2() { grep -q 'status.*ok' cvg/serve/api/tests/test_health.py; }
```

## Validation Card
```yaml
success_criteria:
  - id: eval_1
    description: the health module parses
    runnable: bash
    check_type: deterministic
    terminal: false
    expected_duration_sec: 2
  - id: eval_2
    description: a test asserts the ok payload
    runnable: bash
    check_type: deterministic
    terminal: true
    expected_duration_sec: 2
retry_policy:
  max_iterations: 8
  circuit_breaker_no_progress: 3
  on_terminal_failure: park_with_context
agent_contract:
  version: 2
  read: [intent, contract]
  produce: [code, test]
  required_tools: [bash, python]
  timeout_minutes: 15
  sandbox_type: host
  output_artifacts: []
  mcp_dependencies: []
  emit: [pass, fail]
  backend_metadata: {}
```

## Exit Check
```bash
eval_1 && eval_2
```
