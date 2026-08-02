---
id: T-20260603-stamp-then-verify
title: Stamp-then-verify — proves the HMAC payload boundary (Tier 1)
status: ready
format_version: 2
effort: S
budget_iterations: 15
agent: any
depends_on: []
touches_paths:
  - README.md
source_note: B2 keyed fixture (v2.2 HMAC envelope)
created: 2026-06-03T00:00:00Z
tags: [fixture, b2, keyed]
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

# Stamp-then-verify — proves the HMAC payload boundary (Tier 1)

> **Why:** Keyed fixture for the B2 HMAC sign-off envelope. This spec is NOT in
> the default no-key oracle. It is stamped under an ephemeral key by
> tests/test-hmac-envelope.sh, then verified immediately. A successful verify
> proves the canonical payload boundary is self-consistent: the MAC reads the
> three signed_off* values the stamper just wrote, excludes the signed_off_sig
> line itself, and does not depend on frontmatter line ordering — so it verifies
> on the very next read (Tier 1, full crypto trust).

## Goal
Prove that safe-to-delegate.sh --stamp produces a signed_off_sig that
validate-task-spec.sh Check 17 immediately verifies at Tier 1 when a signing key
is present.

## Context
B2 keyed fixture. Stamped + verified by tests/test-hmac-envelope.sh with an
ephemeral TASKSPEC_SIGNING_KEY. With NO key it degrades to Tier 2 (structural
only), which is why it is excluded from the default no-key oracle.

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
- **Don't ship this fixture as a real task.** It is a keyed regression artifact for the B2 HMAC envelope.
- **Don't add it to the default no-key oracle.** Without a key it is Tier 2, not Tier 1; the keyed behaviour belongs in tests/test-hmac-envelope.sh.
- **Don't hand-edit signed_off_sig.** The autonomy contract is produced by safe-to-delegate.sh --stamp.

## Do-Not-Touch
- src/

## Open Questions
(none — see references/concepts/signed-off.md "The three tiers")
