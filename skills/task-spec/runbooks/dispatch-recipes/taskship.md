# Dispatch Recipe: taskship

> **Use when:** `execution_backend: taskship` — hand the spec to the taskship runtime, which honors the `execution_backend:` frontmatter field as a routing hint and consumes the rest of the spec as its own native task definition.

taskship is one of the agentic systems the Task-Spec format was explicitly designed to interoperate with. Its CLI knows how to parse the v2.1 frontmatter and treats `signed_off: true` as the authorization gate.

---

## Prerequisites

- `taskship` CLI installed and on PATH (verify with `taskship --version`).
- taskship workspace initialized in the repo (`taskship init` has been run; `.taskship/` exists).
- Spec is at `signed_off: true` with the gate clean.
- The spec's `execution_backend:` field is set to `taskship` so the routing hint matches.
- Working tree clean.

---

## Dispatch command

The canonical invocation hands the spec file to the taskship runner:

```bash
taskship run tasks/T-<spec>.md
```

For batch or queued dispatch:

```bash
taskship enqueue tasks/T-<spec>.md
taskship worker --concurrency 2
```

taskship reads `execution_backend:` to pick its internal worker pool (Python, shell, browser-driven). The spec's `agent_contract` block tells the worker which files it may read vs write.

---

## Status reporting

taskship flips `status:` automatically on success or failure. To inspect:

```bash
taskship status tasks/T-<spec>.md
taskship log <run-id>
```

Out-of-band, the canonical Task-Spec status flip script remains the source of truth — taskship calls it internally:

```bash
grep '^status:' tasks/T-<spec>.md
```

---

## Failure modes

| Symptom | Action |
|---------|--------|
| `taskship: spec is not signed_off` | The CLI refuses to dispatch — run the gate first |
| `taskship: execution_backend mismatch` | Spec declares a different backend; either retag or use the matching recipe |
| Worker exits 1 with eval failure log | Inspect `taskship log <run-id>`; treat as defect if evals run pre-dispatch |
| `taskship worker` hangs without progress | Inspect `.taskship/state/`; cancel with `taskship cancel <run-id>` |
| Worker completes but `status:` stays `in-progress` | Manually flip via `transition-status.sh`; file a taskship issue |

---

## See also

- [../dispatching-a-task-spec.md](../dispatching-a-task-spec.md) — router and pre-flight checklist
- [anthive.md](anthive.md) — sibling agentic runtime with parallel-session support
- [../../references/concepts/agent-contract.md](../../references/concepts/agent-contract.md) — what the taskship worker honors
- [../../references/concepts/signed-off.md](../../references/concepts/signed-off.md) — autonomy contract
