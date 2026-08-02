# Eval-Driven Development (EDD)

> **Purpose**: The methodology behind Task-Spec v3. Specs that verify themselves.
> **Confidence**: HIGH (foundational principle)
> **MCP Validated**: 2026-05-19

## The one-sentence definition

> **EDD is the discipline of writing the success criteria as runnable code BEFORE writing the implementation — and letting the agent loop on those criteria until they pass.**

It's TDD's conceptual descendant, applied to agentic tasks.

## The lineage EDD belongs to

| Practice | Unit reframed | Why it worked |
|----------|---------------|---------------|
| Test-Driven Development (TDD) | Tests come first, code is judged by them | Tests are executable specs |
| Infrastructure-as-Code (IaC) | Config is executable, not described | Reproducibility |
| Data contracts in DBT | Quality assertions ARE the spec | Failures caught at write-time, not read-time |
| Type systems | Types are checked, not asserted in prose | Mechanical validation |
| **EDD** | Evals come first, agent loops until they pass | Specs that verify themselves |

## Three core principles

### 1. Executable success criteria

Every Task-Spec MUST have runnable bash evals. Prose alone is rejected by `validate-task-spec.sh`.

```bash
# This is what a Task-Spec promises:
eval_1() { curl -fs http://localhost:8000/health | jq -e '.status == "ok"'; }
eval_2() { test -f docs/runbook.md && grep -qi "rollback" docs/runbook.md; }
eval_3() { pytest tests/test_health.py -q; }
```

Each eval returns 0 (pass) or non-zero (fail). The shell exit code IS the contract.

### 2. Closed-loop verification at agent cadence

The agent executes the task, runs the evals, and **loops on failure** — without human intervention.

```text
loop until pass-or-budget-exhausted:
   1. read intent + last failure context
   2. execute (write code / docs / config)
   3. run all evals
   4. if all pass: terminate as done
   5. if any fail: append failure context, retry
```

The human enters at intent-setting and PR-review. Not in the middle.

### 3. Vendor-portable contract

Markdown + YAML + bash is the universal substrate. Any agentic tool that can
read markdown, parse YAML, and execute bash can consume a Task-Spec — any
conformant engine (e.g. Claude, Codex, Cursor — adapters in
runbooks/dispatch-recipes/), a manual human, or a future tool.

This eliminates vendor lock-in at the unit-of-work layer.

## What EDD is NOT

| Misconception | Reality |
|---------------|---------|
| EDD replaces SDD | No — EDD handles S/M tasks; SDD handles L/XL and subjective work |
| EDD eliminates human review | No — humans review the PR, just not the loop |
| EDD eliminates failure | No — but failure becomes VISIBLE (parked with context) |
| EDD requires special tooling | No — bash + markdown + YAML, that's it |
| EDD is just "tests in tasks" | No — evals also include infra checks, doc presence, behavior probes |

## When EDD wins

See `edd-vs-sdd-honest-comparison.md` for the full breakdown. Short version:

- ✅ S/M effort tasks
- ✅ Output has bash-checkable success criteria
- ✅ Cross-vendor portability matters
- ✅ Autonomous/overnight execution
- ✅ Need for forensic audit trail (every iteration logged)

## When EDD loses

- ❌ Subjective outputs (UI feel, copy quality, design)
- ❌ L/XL multi-day work
- ❌ Pure exploration ("what would this look like?")
- ❌ Tasks where evals can be gamed cheaply (Goodhart's Law)

## The Goodhart guard

The biggest failure mode of EDD: agents game the evals.

> "If port 8000 returns 200, the agent makes ANY endpoint return 200 — even an empty one."

Mitigations:

1. **Multiple evals per task** — minimum 3, ordered from cheap to expensive
2. **Behavioral evals, not just presence evals** — check actual output, not just "thing exists"
3. **PR review still required** — humans still see the diff
4. **Anti-patterns in Zone 3** — explicitly forbid known gaming patterns

Evals catch most failures. Humans catch the rest at PR review. Together they're stronger than either alone.

## Related

- [task-spec-v1.md](task-spec-v1.md) — the format that embodies EDD
- [edd-vs-sdd-honest-comparison.md](edd-vs-sdd-honest-comparison.md) — routing rules
- [agent-contract.md](agent-contract.md) — the loop contract
- [../patterns/runnable-bash-evals.md](../patterns/runnable-bash-evals.md) — eval writing patterns
