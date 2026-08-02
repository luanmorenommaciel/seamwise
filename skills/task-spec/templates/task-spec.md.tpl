---
id: {{ID}}
title: {{TITLE}}
status: {{STATUS}}
format_version: 3
profile: {{PROFILE}}  # lite | standard | full — scales required zones to effort/blast-radius (see references/concepts/profiles.md)
effort: {{EFFORT}}  # LEAF: XS|S|M → Kimi ; L → GLM (execution_backend: glm) . NODE: XL|XXL → add a children: block, decompose (see references/concepts/effort-gate.md)
budget_iterations: {{BUDGET_ITERATIONS}}
agent: {{AGENT}}
parent: (none)  # FEATURE-altitude PRD/SDD this task decomposes from (path or url); the task DISTILLS it, never embeds it
depends_on: {{DEPENDS_ON}}
touches_paths:
{{TOUCHES_PATHS_YAML}}
source_note: {{SOURCE_NOTE}}
created: {{CREATED}}
tags: {{TAGS}}
owner: (none)
priority: {{TODO_PRIORITY}}
severity: {{TODO_SEVERITY}}  # cosmetic | refactor | feature | bugfix | security | financial-critical
due_date: {{TODO_DUE_DATE}}
precondition: (none)
blocked_reason: (none)
security_class: (none)
source_action_item: (none)
tracker_ref: (none)  # backlink to the tracker issue this task registers as (<tracker>:<ref>, e.g. linear:ENG-42, github:#42). Written BACK by Register ① (task-specs-to-issues) after upsert, never by the author. The issue-side marker is the idempotency key, so (none) is fine.
execution_backend: any  # OPEN STRING — names the canonical executor (any|claude|codex|kimi|glm|gemini|<your-harness>). Adapters live in runbooks/dispatch-recipes/ (non-normative). Required to be 'glm' for effort: L.
signed_off: false  # flipped true by safe-to-delegate.sh — the autonomy contract; nothing runs unattended without it
signed_off_by: (none)  # who/what signed off (e.g. luan, safe-to-delegate.sh)
signed_off_at: (none)  # ISO-8601 timestamp of sign-off
accepted: false  # flipped true by accept-task.sh AFTER execution — closes the loop (evals re-run from clean checkout + blast-radius + envelope)
accepted_by: (none)
accepted_at: (none)
---

# {{TITLE}}

> **Why:** {{WHY_ONE_PARAGRAPH}}

---

## Goal

{{GOAL_ONE_PARAGRAPH}}

---

## Context

{{CONTEXT_LEAN_MAX_100_LINES}}

For the feature-level PRD/design this task decomposes from, see the `parent:`
frontmatter field — that document is REFERENCED, never copied here. Zone 1 carries
only the one-paragraph distillation needed to execute this atomic unit.

---

## Behavior

Given/When/Then scenarios the implementation must satisfy. Each scenario has a
stable `B-N` id; every eval in the Validation Card declares which behavior(s) it
`verifies:`, and the validator enforces the chain both ways (no orphan behavior,
no orphan eval). Lite-profile specs may omit this section.

- **B-1** — GIVEN {{B1_GIVEN}} WHEN {{B1_WHEN}} THEN {{B1_THEN}}
- **B-2** — GIVEN {{B2_GIVEN}} WHEN {{B2_WHEN}} THEN {{B2_THEN}}

(Replace with `(none — lite profile, behavior implied by evals)` only on a lite-profile spec.)

---

## Success Criteria

Each criterion is a runnable bash function returning 0 (pass) or non-zero (fail).
Each MUST be terminal (deterministic, idempotent, non-flaky).

```bash
# eval-1: {{EVAL_1_DESCRIPTION}}
eval_1() {
  {{EVAL_1_BASH}}
}

# eval-2: {{EVAL_2_DESCRIPTION}}
eval_2() {
  {{EVAL_2_BASH}}
}

# eval-3: {{EVAL_3_DESCRIPTION}}
eval_3() {
  {{EVAL_3_BASH}}
}
```

---

## Validation Card

```yaml
success_criteria:
  # check_type: deterministic (default, bash-checked, preferred) | llm_judge
  # (subjective criteria graded by a fast LLM via judge_prompt — deterministic-first).
  # verifies: the behavior id(s) this eval proves. Standard/full profiles require
  # every B-N to be covered by >=1 eval and every eval to map to a behavior.
  - id: eval_1
    description: {{EVAL_1_DESCRIPTION}}
    runnable: bash
    check_type: deterministic
    verifies: [B-1]
    terminal: true
    expected_duration_sec: {{EVAL_1_DURATION}}
  - id: eval_2
    description: {{EVAL_2_DESCRIPTION}}
    runnable: bash
    check_type: deterministic
    verifies: [B-2]
    terminal: true
    expected_duration_sec: {{EVAL_2_DURATION}}
  - id: eval_3
    description: {{EVAL_3_DESCRIPTION}}
    runnable: bash
    check_type: deterministic
    verifies: [B-1, B-2]
    terminal: true
    expected_duration_sec: {{EVAL_3_DURATION}}

retry_policy:
  max_iterations: {{BUDGET_ITERATIONS}}
  circuit_breaker_no_progress: 3
  on_terminal_failure: park_with_context

agent_contract:
  version: 2
  read: [intent, behavior, contract, guardrails, operations]
  produce:
    - code
    - docs
    - config
    - tests
  required_tools: [git, bash]
  timeout_minutes: 30
  sandbox_type: host  # host | isolated | ephemeral
  output_artifacts: []
  mcp_dependencies: []
  emit:
    - pass
    - fail
    - retry_with_reason
    - parked_with_context
  backend_metadata: {}  # optional executor-specific key/value map (the backend names itself); replaces the old codex_metadata/kimi_metadata
```

---

## Exit Check

```bash
# Final proof-of-done. Returns 0 only when ALL evals pass.
eval_1 && eval_2 && eval_3
```

---

## Rollback Plan

If execution fails mid-task, revert to the pre-task state:

1. **Git revert** — `git revert --no-commit HEAD` (if commits were made)
2. **File restore** — `git checkout -- <paths>` for any modified files not yet committed
3. **State reset** — update task status to `parked` and record `blocked_reason`

{{ROLLBACK_SPECIFIC_STEPS}}

(Replace with `(none — this task is append-only or additive with no destructive changes)` if no rollback is needed. Full profile requires concrete steps.)

---

## Observability Hooks

What to watch during execution and after deployment:

- **Expected duration:** {{OBSERVABILITY_EXPECTED_DURATION}}
- **Key metric:** {{OBSERVABILITY_KEY_METRIC}}
- **Alert condition:** {{OBSERVABILITY_ALERT_CONDITION}}
- **Log tail:** {{OBSERVABILITY_LOG_TAIL}}

(Replace with `(none — no runtime observability required)` if not applicable. Full profile requires real hooks.)

---

## Anti-Patterns

- **Don't {{ANTI_1_ACTION}}** — {{ANTI_1_REASON}}. {{ANTI_1_INSTEAD}}.
- **Don't {{ANTI_2_ACTION}}** — {{ANTI_2_REASON}}. {{ANTI_2_INSTEAD}}.
- **Don't {{ANTI_3_ACTION}}** — {{ANTI_3_REASON}}. {{ANTI_3_INSTEAD}}.

---

## Do-Not-Touch

Files the executor MUST NOT modify:

{{DO_NOT_TOUCH_LIST}}

---

## Open Questions

Things the executor should resolve DURING build, not assume:

1. **{{QUESTION_1}}** — {{QUESTION_1_CONTEXT}}
2. **{{QUESTION_2}}** — {{QUESTION_2_CONTEXT}}

(Replace with `(none — this task is fully specified)` if no open questions remain.)
