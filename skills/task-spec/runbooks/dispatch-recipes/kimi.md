# Dispatch Recipe: Kimi CLI (via broker)

> **Use when:** `execution_backend: kimi` — the dark-factory path. The Kimi broker wraps Kimi CLI with a 12-stage pipeline that injects context, runs a Codex plan review, executes Kimi, validates via API, and captures a telemetry envelope.

This is the most heavily instrumented dispatch path in the skill: every stage emits a typed exit code and the broker writes a telemetry envelope the dispatcher can pull post-run.

---

## Prerequisites

- Kimi CLI installed and authenticated (`kimi --version`).
- `kimi-plugin-cc` installed (provides `/kimi:crank`, `/kimi:status`, `/kimi:result`).
- Spec is at `signed_off: true` with the gate clean.
- Working tree clean — the broker's origin-state check rejects dirty trees.
- Local branch is in sync with origin (`git fetch && git status` reports no divergence) — broker stage 1 will refuse otherwise.

---

## Dispatch command

Single-task dispatch with the full diff-review pipeline:

```bash
/kimi:crank tasks/T-<spec>.md --tag <feature-name> --diff-review
```

Batch dispatch (dependency-respecting waves):

```bash
/kimi:crank-batch 'tasks/T-2026*.md'
```

Highest-priority ready task:

```bash
/kimi:crank-next
```

The 12-stage broker pipeline runs: origin-state check → preflight → context injection (CLAUDE.md + scoped rules) → library docs (Context7) → plan review (Codex) → Kimi execution → API validation → diff review (Codex) → telemetry capture → status flip.

---

## Status reporting

The broker flips `status:` automatically at stage boundaries. Out-of-band inspection:

```bash
/kimi:status                          # All sessions
/kimi:status --session-id <id>        # Specific session
/kimi:result --session-id <id>        # Telemetry envelope (post-completion)
```

The telemetry envelope is JSON with the eval pass/fail summary, plan-review and diff-review verdicts, total tokens, and the originating spec path.

---

## Failure modes

| Exit code | Meaning | Action |
|-----------|---------|--------|
| 2 | `origin-diverged` — local branch out of sync during dispatch | `git pull --rebase`; re-dispatch |
| 3 | `buggy-evals` — a new lint or preflight rejected the spec | Re-run `safe-to-delegate.sh --stamp` against latest rules |
| 5 | `checkpoint-conflict` — stale resume checkpoint blocks new session | Inspect `.kimi/state/checkpoints/`; restore or delete and re-dispatch |
| 6 | `diff-review-rejected` — Codex rejected Kimi's diff post-execution | Read the review verdict; the broker has already parked the task |
| Telemetry missing | Broker pipeline hang | `/kimi:cancel <session-id>`; inspect `.kimi/state/`; file an issue against `kimi-plugin-cc` |

---

## See also

- [../dispatching-a-task-spec.md](../dispatching-a-task-spec.md) — router and pre-flight checklist
- [claude-code.md](claude-code.md) — Claude can drive `/kimi:crank` from inside its own session
- [codex.md](codex.md) — Codex is the plan-review and diff-review engine inside the Kimi broker
- [../../references/concepts/agent-contract.md](../../references/concepts/agent-contract.md) — read-zone semantics
