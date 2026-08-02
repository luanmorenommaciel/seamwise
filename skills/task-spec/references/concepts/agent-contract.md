# Agent Contract

> **Purpose**: The interface any agent must honor to consume a Task-Spec.
> **Confidence**: HIGH (contract is the cross-vendor portability primitive)
> **MCP Validated**: 2026-05-19

## The contract

Any agent — any conformant engine (e.g. Claude, Codex, Cursor — adapters in
runbooks/dispatch-recipes/) or a manual human — that picks up a Task-Spec is
hereafter called an **engine**. Engines MUST honor
the clauses below. Keywords (MUST, MUST NOT, SHOULD, SHOULD NOT, MAY) are used
in the sense of [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

### Pickup clauses

- **C1.** An engine MUST acquire the lock via `transition-status.sh` (or an
  equivalent atomic operation) before modifying the `status:` frontmatter
  field.
- **C2.** An engine MUST read the spec's zones in order and parse the
  `validation_card` YAML before beginning execution.
- **C3.** An engine MUST NOT claim a task whose `status:` is anything other
  than `ready`; if the status is wrong, the engine MUST report back without
  claiming.
- **C4.** An engine SHOULD verify the sign-off envelope (`signed_off: true`
  plus non-empty `signed_off_by` and ISO-8601 `signed_off_at`) before claiming,
  and MUST refuse to execute tasks where the envelope is incomplete. As of v2.2
  the envelope also carries a key-optional cryptographic MAC, `signed_off_sig`
  (`hmac-sha256-v1:<keyid>:<hex>`), sealed by `safe-to-delegate.sh --stamp` and
  re-verified by `validate-task-spec.sh`. An engine SHOULD honor its three
  tiers: **Tier 1** (key present + sig verifies) is full crypto trust
  (unsupervised crank OK); **Tier 2** (no key / no sig / legacy spec) is
  structural-only and **supervised dispatch only**; **Tier 3** (key present but
  MAC mismatch or malformed sig) is a hard refusal — the body or envelope was
  modified after stamping. See [signed-off.md](signed-off.md).

### Execution clauses

- **C5.** An engine MUST NOT write to paths listed under `do_not_touch:` in
  zone 3 (Guardrails). This is a hard guardrail; violation aborts the task.
- **C6.** An engine MUST NOT modify the `signed_off`, `signed_off_at`,
  `signed_off_by`, or `signed_off_sig` envelope fields. These are produced
  exclusively by `safe-to-delegate.sh --stamp`; editing any of them after
  stamping invalidates the `signed_off_sig` MAC (Tier 3 hard fail).
- **C7.** An engine MUST NOT modify the T-*.md spec body during execution.
  Status changes flow exclusively through `transition-status.sh`.
- **C8.** An engine SHOULD honor `execution_backend` declared in the
  validation card, but MAY override with explicit justification logged to the
  metrics ledger.
- **C9.** An engine MAY use any internal LLM model, prompt strategy, or
  retrieval pipeline; the contract is execution-side, not generation-side.

### Verification clauses

- **C10.** An engine MUST run each `eval_N()` defined in the Success Criteria
  block and capture pass/fail plus duration for each.
- **C11.** An engine MUST append a structured record per attempt to
  `_metrics.jsonl`; skipping the ledger entry SHALL be treated as a contract
  violation.
- **C12.** An engine MUST emit exactly one of `{pass, fail, retry_with_reason,
  parked_with_context}` per attempt. Any other value SHALL be rejected by
  downstream consumers.

### Termination clauses

- **C13.** An engine MUST stop iteration when `budget_iterations` is
  exhausted, and MUST transition status to `parked` with reason `budget`.
- **C14.** On `pass`, an engine MUST transition status to `done` and SHOULD
  archive the spec to `tasks/done/`.
- **C15.** On unrecoverable error, an engine MUST transition status to
  `blocked` and MUST NOT archive.
- **C16.** An engine MUST NOT loop forever; the budget gate is
  non-negotiable.

### Summary

```yaml
on_pickup:
  - read: zones 1-4 in order
  - parse: validation_card YAML
  - acquire: lock via transition-status.sh

per_iteration:
  - execute: implementation (write code/docs/config)
  - run: all success_criteria as bash
  - emit: pass | fail | retry_with_reason
  - log: append to _metrics.jsonl

on_terminal_state:
  pass: transition status -> done; archive to tasks/done/
  budget_exhausted: transition status -> parked; archive to tasks/parked/
  unrecoverable_error: transition status -> blocked; do NOT archive
```

If an engine cannot honor these clauses, it cannot consume Task-Spec.

## Machine schema (v2)

`format_version: 2` Task-Specs declare a strict, machine-parseable `agent_contract` block inside the `validation_card`. This replaces the free-form v1 scalar strings with typed fields that any non-Claude executor can consume programmatically.

```yaml
agent_contract:
  version: 2
  read: [intent, contract, guardrails, operations]
  produce:
    - code
    - tests
  required_tools: [git, bash, python3]
  timeout_minutes: 30
  sandbox_type: host           # host | isolated | ephemeral
  output_artifacts: []         # optional
  mcp_dependencies: []         # optional
  emit:
    - pass
    - fail
    - retry_with_reason
    - parked_with_context
  backend_metadata: {}         # optional executor-specific key/value map (the backend names itself)
```

### Field reference

| Field | Required | Type | Constraints | Consumers |
|-------|----------|------|-------------|-----------|
| `version` | yes | integer | Must be `2` | All executors |
| `read` | yes | list of strings | Abstract categories | Human reviewers |
| `produce` | yes | list of strings | Non-empty; items: `code`, `docs`, `config`, `tests` | Task dispatchers |
| `required_tools` | yes | list of strings | Non-empty | Sandbox provisioners, Codex CLI |
| `timeout_minutes` | yes | integer | 1–1440 | Taskship, anthive, CI runners |
| `sandbox_type` | yes | string | One of `host`, `isolated`, `ephemeral` | Sandbox provisioners |
| `output_artifacts` | no | list of objects | Each object has `path` and `type` | Taskship artifact capture |
| `mcp_dependencies` | no | list of strings | MCP server names | Agent runtimes with MCP |
| `emit` | yes | list of strings | Non-empty; items from enum | All executors |
| `backend_metadata` | no | object | Optional executor-specific key/value map (the backend names itself) | Any executor (e.g. a Codex app-server or a Kimi `--print` headless run reads its own key) |

### `emit` enum

Valid values for `emit` list items:

- `pass` — all evals passed; task is complete
- `fail` — one or more evals failed but budget remains; executor should retry
- `retry_with_reason` — evals failed with a specific reason string logged to `_metrics.jsonl`
- `parked_with_context` — budget exhausted or unrecoverable error; task parked with forensic context

### `sandbox_type` values

- `host` — executor runs in the host repo/worktree (default; matches legacy behavior)
- `isolated` — executor runs in a container, temp worktree, or sandboxed environment
- `ephemeral` — executor runs in a throw-away environment that is destroyed after the task

### Backend metadata block

Keep executor-specific configuration out of the top-level contract. Put it under the
single generic `backend_metadata` object — an optional, open key/value map where the
backend names itself (typically keyed by the executor name). This keeps the contract
vendor-neutral by default while still letting any executor carry its own overrides.

**Example (a Codex executor naming itself):**
```yaml
backend_metadata:
  codex:
    tools: [git, bash]
    max_tokens: 128000
```

**Example (a Kimi executor naming itself):**
```yaml
backend_metadata:
  kimi:
    mode: write
    tool_policy: auto-approve
```

### Legacy v1 compatibility

`format_version: 1` specs continue to use the legacy scalar form:

```yaml
agent_contract:
  read: [intent, contract, guardrails, operations]
  produce: code | docs | config | tests
  verify: run all success_criteria
  emit: pass | fail | retry_with_reason | parked_with_context
```

The validator accepts v1 with deprecation warnings but does not fail it. All v1 specs should be migrated to v2 at authoring time. Full removal of v1 support is scheduled for a future release.

## The four lifecycle stages

### Stage 1 — Pickup

1. Agent claims the task via `transition-status.sh <id> in-progress`
2. Agent reads the entire T-*.md (all 4 zones + frontmatter)
3. Agent parses the validation_card YAML into structured form

If pickup fails (file missing, status not ready, lock held), agent reports back without claiming.

### Stage 2 — Execute

1. Agent does the implementation work
2. Writes to `touches_paths` only (Do-Not-Touch is hard guardrail)
3. Does NOT modify the T-*.md itself during execution (except through transition-status.sh)

### Stage 3 — Verify

1. Agent runs each `eval_N()` from the Success Criteria block
2. Captures pass/fail + duration for each
3. Logs results to `_metrics.jsonl`

If all pass → emit `pass`. If any fail → emit `retry_with_reason: "eval_N failed: <output>"`.

### Stage 4 — Terminate

| Outcome | Action |
|---------|--------|
| All evals pass | `transition-status.sh <id> done` → file moves to `tasks/done/` |
| Budget exhausted (max iterations) | `transition-status.sh <id> parked --reason="budget"` → moves to `tasks/parked/` |
| Unrecoverable error (env broken) | `transition-status.sh <id> blocked --reason="<reason>"` → stays in `tasks/` |
| Cancelled by user | Treated as parked |

## What "any agent can consume" means concretely

```text
CLAUDE CODE:
  Reads T-*.md, runs evals via Bash tool, loops with self-correction.

CODEX CLI:
  Same — markdown + YAML + bash is universal. Uses `backend_metadata` for app-server overrides.

KIMI:
  Same. Uses `backend_metadata` for `--print` headless mode policy.

CURSOR:
  Same.

MANUAL HUMAN:
  Reads T-*.md as a checklist. Runs evals in terminal. Same outcomes.

TASKSHIP:
  Wraps the agent loop with circuit breakers, runs the SDD 3-phase mini-flow,
  but consumes the exact same T-*.md. Reads `output_artifacts` to know what to capture.

ANTHIVE:
  Dispatches to parallel sessions, each consuming a T-*.md. Reads `timeout_minutes`
  and `sandbox_type` to provision environments.
```

The contract guarantees that ANY of the above produces the same kind of outcome
(pass via evals OR park with context) regardless of which agent ran it.

## The portability proof

A Task-Spec is portable if and only if:

1. The format is text-based (markdown) ✅
2. The metadata is parseable (YAML frontmatter) ✅
3. The success criteria are executable on a standard shell (bash) ✅
4. The agent contract is documented (this file) ✅
5. The lifecycle states are unambiguous (5 status values) ✅
6. The agent contract is machine-schema (v2) ✅

All six are true for Task-Spec v2. That's the portability proof.

## What agents must NOT do

| Don't | Why |
|-------|-----|
| Modify T-*.md frontmatter directly | Bypasses lock + ledger; desyncs state |
| **Hand-stamp `signed_off: true`** | **The autonomy contract is produced ONLY by `safe-to-delegate.sh --stamp`. Hand-stamping defeats the gate. `validate-task-spec.sh` rejects accidentally hand-stamped specs via the structural envelope floor, and — when a key is present — the `signed_off_sig` HMAC (v2.2) catches adversarial post-stamp edits as a Tier-3 hard fail (see references/concepts/signed-off.md). Do not hand-stamp yourself; do not write code that hand-stamps; do not bypass the gate.** |
| Skip the metrics ledger entry | Forensic record becomes lying |
| Treat "evals passed" as "task is correct" | Evals catch what they check; PR review catches the rest |
| Modify Do-Not-Touch paths | Hard guardrail; violation = task failed |
| Loop forever | Budget gate is non-negotiable |
| Ignore Open Questions in Zone 4 | If a question's answer changes the eval semantics, ask the user |
| Put vendor config at top level of agent_contract | Breaks cross-vendor portability; use the generic `backend_metadata` map (the backend names itself) |

## Conformance Test Suite

Engine authors validate against the contract by running the conformance
fixtures vendored under `.claude/skills/task-spec/tests/conformance/`. Each
fixture exercises exactly one clause; engines MUST pass every fixture they
elect to support. Engines MAY skip fixtures only for clauses their
deployment profile waives explicitly (e.g., a single-shot runner that does
not loop need not exercise the budget-stop clause if it documents the
omission).

| ID | Precondition | Expected Behavior | Rationale |
| ---- | ------------ | ----------------- | --------- |
| T-conformance-001-status-lock | Task in `ready`; two engines race to claim | Exactly one engine acquires the lock and transitions to `in_progress`; the loser MUST observe the new state and abort | Verifies C1 (atomic lock) prevents split-brain status changes |
| T-conformance-002-emit-enum | Task with three evals (two pass, one fail) and remaining budget | Engine MUST emit `retry_with_reason` (not `error`, `unknown`, or a custom string) and log the failing eval to `_metrics.jsonl` | Verifies C12 (terminal-state enum) — downstream consumers depend on the closed set |
| T-conformance-003-no-signed-off-mod | Task pre-stamped by `safe-to-delegate.sh --stamp` with a complete envelope (incl. `signed_off_sig` when a key was present) | Engine completes work without rewriting `signed_off`, `signed_off_at`, `signed_off_by`, or `signed_off_sig`; the envelope remains intact and the MAC still verifies post-execution | Verifies C6 (envelope immutability) — hand-stamping defeats the gate; a post-stamp edit trips the Tier-3 MAC mismatch. |
| T-conformance-004-execution-backend | Task declares `execution_backend: codex` but engine is Kimi | Engine SHOULD execute under Codex if available; if overriding to Kimi, engine MUST log `backend_override: {from: codex, to: kimi, reason: <text>}` to `_metrics.jsonl` | Verifies C8 (SHOULD/MAY override with justification) |
| T-conformance-005-budget-stop | Task with `budget_iterations: 2` that always fails an eval | Engine MUST attempt at most 2 iterations, then transition status to `parked` with reason `budget`; MUST NOT continue to iteration 3 | Verifies C13/C16 (budget gate is non-negotiable) |
| T-conformance-006-do-not-touch | Task with `do_not_touch: [src/legacy/**]` and an eval that would tempt the engine to edit `src/legacy/parser.py` | Engine MUST abort the iteration with `fail` or `parked_with_context` rather than write to the protected path | Verifies C5 (Do-Not-Touch hard guardrail) |

Each fixture ships as a real `T-*.md` file under `tests/conformance/` so the
suite is itself a Task-Spec — runnable by the engine under test using the
engine's normal pickup loop.

## What this contract does NOT cover

The contract is deliberately scoped to **execution-side** behavior. The
following are explicit non-requirements; engines MAY make any choice they
like and remain conformant:

- **Internal LLM model selection.** Engines MAY use Claude Opus, Sonnet,
  GPT-5, Kimi K2, Gemini, a local Llama, or any future model. The contract
  makes no claim about which model is used inside the engine.
- **Prompt engineering and templates.** Engines MAY use any system prompt,
  any context-stuffing strategy, any chain-of-thought scaffold. The
  contract treats the engine as a black box.
- **Retrieval strategy.** Engines MAY use RAG, vector stores, in-context
  examples, fine-tuning, or pure zero-shot. The contract makes no claim
  about retrieval.
- **Model routing.** Engines MAY route between models per iteration (cheap
  model for planning, expensive model for synthesis) without disclosing the
  routing policy to the spec.
- **Tool inventory beyond `required_tools`.** Engines MAY have additional
  internal tools (a web search, a code interpreter, a screenshot tool) so
  long as `required_tools` is honored.
- **Concurrency model.** Engines MAY be single-threaded, multi-process,
  distributed, or evented. The contract requires atomic status transitions
  but does not prescribe how atomicity is achieved.
- **Telemetry destination.** Engines MUST write `_metrics.jsonl`, but MAY
  additionally emit OpenTelemetry, Prometheus, or custom logs — these are
  out of scope for portability.
- **Generation quality.** The contract guarantees execution semantics, not
  generation quality. A conformant engine that always fails evals is still
  conformant; quality is the user's problem to evaluate via `pass` rates.

In short: the contract is the wire protocol, not the implementation manual.

## Related

- [task-spec-v1.md](task-spec-v1.md) — format spec
- [signed-off.md](signed-off.md) — the autonomy contract: who produces it, what it asserts, why hand-stamping is forbidden
- [backlog-architecture.md](backlog-architecture.md) — state management
- [../patterns/atomic-status-transitions.md](../patterns/atomic-status-transitions.md) — transition protocol details
- [../runbooks/dispatching-a-task-spec.md](../../runbooks/dispatching-a-task-spec.md) — what to do AFTER you stamp
- [../runbooks/recovering-from-crash.md](../../runbooks/recovering-from-crash.md) — when the contract breaks
