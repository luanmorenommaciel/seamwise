# Pattern: Validation Card YAML

> **Purpose**: Machine-parseable mirror of the bash evals. The contract.
> **MCP Validated**: 2026-05-19

## What it is

A YAML block in the Contract zone of every Task-Spec that machine-readably describes:
- Each eval (id, description, runtime estimate, and the behavior it `verifies:`)
- Retry policy (max iterations, circuit breaker)
- Agent contract (the typed v2 schema — see [agent-contract.md](../concepts/agent-contract.md))

```yaml
success_criteria:
  - id: eval_1
    description: Docker stack reaches healthy state
    runnable: bash
    verifies: [B-1]
    terminal: true
    expected_duration_sec: 60
  - id: eval_2
    description: Langfuse UI reachable
    runnable: bash
    verifies: [B-2]
    terminal: true
    expected_duration_sec: 5

retry_policy:
  max_iterations: 15
  circuit_breaker_no_progress: 3
  on_terminal_failure: park_with_context

agent_contract:
  version: 2
  read: [intent, contract, guardrails, operations]
  produce:
    - code
    - tests
  required_tools: [git, bash, docker]
  timeout_minutes: 30
  sandbox_type: host           # host | isolated | ephemeral
  emit:
    - pass
    - fail
    - retry_with_reason
    - parked_with_context
  backend_metadata: {}         # optional executor-specific map (the backend names itself)
```

## Why YAML + bash both?

The bash evals are HOW to verify. The YAML card is WHAT each eval checks, in
machine-parseable form. Executors use the YAML to:

- Display progress: "Running eval_2: Langfuse UI reachable... (5s expected)"
- Estimate budget: sum of expected_duration_sec * max_iterations = upper bound
- Route results: machine-parseable pass/fail per eval_id
- Build metrics: log each eval's duration to `_metrics.jsonl`

Without the YAML, executors would have to parse bash function names to display
progress. With it, the contract is explicit.

## Field reference

### success_criteria

| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `id` | string | yes | Must match the bash function name (`eval_1`, `eval_2`, ...) |
| `description` | string | yes | One-line WHY this eval exists |
| `runnable` | enum | yes | `bash` (default) or `llm_judge` (see Check type below) |
| `verifies` | list | yes on `standard`/`full` | The `B-N` behavior(s) this eval proves; every `B-N` needs ≥1 eval and every `verifies:` must name a declared behavior ([profiles.md](../concepts/profiles.md)) |
| `terminal` | bool | yes | Must be `true` (idempotent + deterministic) |
| `expected_duration_sec` | int | yes | Realistic estimate; powers budget + progress UI |

### retry_policy

| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `max_iterations` | int | yes | Hard cap on loop count (default 15) |
| `circuit_breaker_no_progress` | int | yes | Halt after N iterations with no eval-pass-count delta |
| `on_terminal_failure` | enum | yes | `park_with_context` (the terminal-failure action) |

### agent_contract (v2 typed schema)

The full field reference lives in [agent-contract.md](../concepts/agent-contract.md);
the load-bearing fields are:

| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `version` | int | yes | Must be `2` |
| `read` | list | yes | Zone categories the engine reads before executing |
| `produce` | list | yes | Artifact kinds: `code`, `docs`, `config`, `tests` |
| `required_tools` | list | yes | Tools the sandbox must provide |
| `timeout_minutes` | int | yes | 1–1440; consumed by dispatchers/CI |
| `sandbox_type` | enum | yes | `host` \| `isolated` \| `ephemeral` |
| `emit` | list | yes | Allowed terminal states (from the `emit` enum) |
| `backend_metadata` | object | no | Executor-specific overrides (the backend names itself) |

## Common mistakes

### Missing field

```yaml
# ❌ no description
success_criteria:
  - id: eval_1
    runnable: bash
```

`validate-task-spec.sh` rejects this. Every eval needs a description.

### Bash function and YAML id mismatch

```bash
eval_one() { ... }   # bash
```

```yaml
success_criteria:
  - id: eval_1      # ❌ "eval_one" not "eval_1"
```

The id MUST match the bash function name verbatim.

### Unrealistic durations

```yaml
- id: eval_pytest_full
  description: Run full test suite
  expected_duration_sec: 1    # ❌ pytest never finishes in 1s
```

Be honest. Budget calculations depend on accuracy.

## YAML inside markdown — formatting

The Validation Card is fenced YAML inside the markdown file:

````markdown
## Validation Card

```yaml
success_criteria:
  - id: eval_1
    description: ...
```
````

`validate-task-spec.sh` finds this block by looking for the `success_criteria:` key
under a `## Validation Card` heading. The fenced YAML language tag (`yaml`) is required.

## Check type: deterministic vs LLM-judged

Most success criteria are **deterministic** — a bash eval returns 0/non-zero with no
judgment required. That is the default and the strongly preferred form, because any
engine (Claude, Codex, Kimi, taskship, a human on a CLI) gets the identical verdict.

But some legitimate criteria cannot be reduced to bash: "the error message is clear
to a new developer," "the API shape is idiomatic," "the migration comment explains
the why." Forcing these into fake `grep` evals produces tautologies that pass while
meaning nothing (the F16 lesson). For these, Task-Spec supports an explicit
**LLM-judged** check — an honest escape hatch, not a loophole.

Declare the class per criterion with the optional `check_type` field:

```yaml
success_criteria:
  - id: eval_1
    description: /health returns 200 + correct JSON
    runnable: bash
    check_type: deterministic        # default; the bash eval is authoritative
    terminal: true
    expected_duration_sec: 2
  - id: eval_2
    description: Error message names the missing field and is actionable
    runnable: llm_judge
    check_type: llm_judge            # graded by a fast impartial LLM
    judge_prompt: >
      Given the error message emitted when a required field is absent, return
      PASS if it names the specific missing field AND suggests a fix; else FAIL
      with a one-line reason.
    terminal: true
    expected_duration_sec: 5
```

Rules of the road:

- **Deterministic-first.** If a criterion *can* be bash-checked, it MUST be. Reserve
  `llm_judge` for genuinely subjective criteria. The validator warns if an
  `llm_judge` criterion looks mechanically checkable.
- **A judge_prompt is mandatory** for `llm_judge` criteria — it is the contract the
  grading LLM honors. No prompt = no judge = invalid.
- **Determinism is a spectrum, not a dodge.** A spec that is >50% `llm_judge` is a
  smell: it is probably SDD work (subjective) misfiled as EDD. The validator warns.
- **Cross-engine portability holds.** Any agent that can call an LLM can run an
  `llm_judge` check; the `judge_prompt` is the portable contract. Deterministic
  checks remain engine-independent bash.

This mirrors the industry convention (AgentContract's `deterministic check` vs
`LLM-judged check`; EDDOps' offline/online evaluation split): make the grading
mechanism explicit so humans, evaluators, and runtimes can all reason about it.

## Related

- [task-spec-v1.md](../concepts/task-spec-v1.md) — format spec
- [runnable-bash-evals.md](runnable-bash-evals.md) — the bash side of the pair
- [agent-contract.md](../concepts/agent-contract.md) — how agents consume the YAML
