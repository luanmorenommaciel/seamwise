---
id: T-20260602-inverted-grep-3
title: Inverted wc fallback
status: ready
format_version: 2
effort: S
budget_iterations: 15
agent: any
depends_on: []
touches_paths:
  - README.md
source_note: WS5 fixture
created: 2026-06-02T00:00:00Z
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
signed_off: false
signed_off_by: (none)
signed_off_at: (none)
---

# Inverted wc fallback

> **Why:** Pattern 3: $(wc -l < file || echo 0) same class as grep -c

## Goal
Synthetic v2.1 fixture used by tests/test-task-spec-skill.sh --suite fixtures.

## Context
WS5 oracle entry; expected verdict declared in tests/fixtures/oracle.json.

## Success Criteria
```bash
eval_1() {
  lines=$(wc -l < /nonexistent || echo 0)
  [ "$lines" -eq 0 ]
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
