---
id: T-20260603-tampered-body
title: Tampered body — Tier 3 hard-fail under a key
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
tags: [fixture, b2, keyed, tamper]
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

# Tampered body — Tier 3 hard-fail under a key

> **Why:** Keyed fixture for the B2 HMAC sign-off envelope. This spec is NOT in
> the default no-key oracle. tests/test-hmac-envelope.sh stamps it under an
> ephemeral key (sealing signed_off_sig), then edits ONE character of the BODY
> below and re-verifies. Because the body_digest in the canonical payload no
> longer matches the sealed MAC, validate-task-spec.sh Check 17 must hard-FAIL
> at Tier 3 with "DO NOT DELEGATE: spec body or envelope modified after
> stamping". With NO key, this same edit is invisible (Tier 2) — which is the
> whole point of the v2.2 crypto upgrade.

## Goal
Prove that any post-stamp modification to the spec body (or to a signed_off*
value) is caught at Tier 3 when a signing key is present.

## Context
B2 keyed fixture. The TAMPER-TARGET line below is the single character the
keyed test mutates after stamping. TAMPER-TARGET: original-marker-do-not-edit

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
- **Don't ship this fixture as a real task.** It is a keyed tamper-detection artifact for the B2 HMAC envelope.
- **Don't add it to the default no-key oracle.** Without a key the tamper is undetectable (Tier 2); the Tier 3 behaviour is proven only in tests/test-hmac-envelope.sh under a key.
- **Don't re-stamp after tampering in the test.** The test asserts the FAIL; re-stamping would mask the regression it guards.

## Do-Not-Touch
- src/

## Open Questions
(none — see references/concepts/signed-off.md "The three tiers")
