---
id: T-20260721-ex-xs-staleness-config
title: "XS example — add the staleness SLA config key"
status: ready
format_version: 3
profile: lite
effort: XS
budget_iterations: 5
agent: any
depends_on: []
touches_paths: []
creates_paths:
  - cvg/serve/config/staleness.yaml
source_note: "effort-gate v3.4 worked example (XS leaf)"
created: 2026-07-21T00:00:00Z
execution_backend: kimi
---

# XS example — add the staleness SLA config key

> **Why XS:** one new file, nothing to read to do it safely, one assertion. A config
> tweak. The smallest runnable atom — an agent needs almost no context.

## Goal
Create `cvg/serve/config/staleness.yaml` declaring `staleness_sla_minutes: 20` (the R-4
freshness SLA the serve lane alerts on).

## Success Criteria
```bash
eval_1() { grep -qE '^staleness_sla_minutes:[[:space:]]*20$' cvg/serve/config/staleness.yaml; }
```

## Validation Card
```yaml
success_criteria:
  - id: eval_1
    description: the SLA key exists with value 20
    runnable: bash
    check_type: deterministic
    terminal: true
    expected_duration_sec: 1
retry_policy:
  max_iterations: 5
  circuit_breaker_no_progress: 2
  on_terminal_failure: park_with_context
agent_contract:
  version: 2
  read: [intent]
  produce: [code]
  required_tools: [bash]
  timeout_minutes: 5
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
