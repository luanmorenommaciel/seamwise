---
id: T-20260603-legacy-no-signoff
title: Legacy pre-v2 spec with no signed_off line at all
status: ready
format_version: 2
effort: S
budget_iterations: 15
agent: any
depends_on: []
touches_paths:
  - README.md
source_note: WS5 fixture
created: 2026-06-03T00:00:00Z
tags: [fixture]
owner: (none)
priority: P2
severity: cosmetic
due_date: (none)
precondition: (none)
blocked_reason: (none)
security_class: (none)
source_action_item: (none)
linear_ref: (none)
execution_backend: any
---

# Legacy pre-v2 spec with no signed_off line at all

> **Why:** Legacy spec authored before v2.1 envelope existed — validate must NOT fire the envelope error (signed_off line absent means default false)

## Goal
Synthetic v2.1.1 fixture used by tests/test-task-spec-skill.sh --suite fixtures.

## Context
WS5 oracle entry; expected verdict declared in tests/fixtures/oracle.json.

## Success Criteria
```bash
eval_1() {
  ! grep -q 'NEVERMATCH' README.md
}
```

## Validation Card
```yaml
success_criteria:
  - id: eval_1
    description: synthetic
    runnable: bash
    check_type: deterministic
    terminal: true
    expected_duration_sec: 1
retry_policy:
  max_iterations: 15
  circuit_breaker_no_progress: 3
  on_terminal_failure: park_with_context
agent_contract:
  version: 2
  read: [intent, contract, guardrails, operations]
  produce:
    - code
  required_tools: [bash]
  timeout_minutes: 30
  sandbox_type: host
  output_artifacts: []
  mcp_dependencies: []
  emit:
    - pass
    - fail
  backend_metadata: {}
```

## Exit Check
```bash
eval_1
```

## Rollback Plan
(none — fixture)

## Observability Hooks
(none — fixture)

## Anti-Patterns
- **Don't ship this fixture** — regression test only.
- **Don't bypass with --skip flags** — lint must fire under defaults.
- **Don't trust the eval** — the whole point is the lint catching it.

## Do-Not-Touch
- src/

## Open Questions
(none — fixture)
