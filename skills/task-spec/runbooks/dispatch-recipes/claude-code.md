# Dispatch Recipe: Claude Code

> **Use when:** `execution_backend: claude` (or `any`, with Claude Code as the operator's chosen executor).

Claude Code consumes a `signed_off: true` spec directly — either invoked from a human prompt or delegated by another Claude session via the `Task()` tool. There is no external broker; the agent reads the spec, honors the `agent_contract` read zones, and applies changes.

---

## Prerequisites

- The spec is at `signed_off: true` (verified via `grep '^signed_off: true' tasks/T-<spec>.md`).
- Re-running `safe-to-delegate.sh` is a no-op (verdict: `DELEGATE`).
- Working tree is clean — Claude's diff must be attributable.
- The Claude session has filesystem write access to all `touches_paths` and `creates_paths` declared in the spec.
- If launched as a subagent, the parent session has the `Task` tool registered.

---

## Dispatch command

From a parent Claude session (delegation pattern):

```text
Task(
  description="Execute T-<spec>",
  prompt="Read tasks/T-<spec>.md. Honor signed_off:true as the autonomy contract. Stay within touches_paths and creates_paths. Run each eval block before claiming done. Flip status: ready -> in-progress -> done via transition-status.sh.",
  subagent_type="general-purpose"
)
```

From a human operator (direct invocation), paste the spec path into the prompt:

```text
Execute tasks/T-<spec>.md per its agent_contract block.
```

Claude reads the `agent_contract.read` zone list (Zones 1, 2, 4, 5) and treats Zones 3 and 6 as advisory but not authoritative for code changes.

---

## Status reporting

Claude is responsible for flipping `status:` at boundaries. Use the canonical script:

```bash
bash .claude/skills/task-spec/scripts/transition-status.sh \
  tasks/T-<spec>.md ready in-progress

# ... do the work, run evals ...

bash .claude/skills/task-spec/scripts/transition-status.sh \
  tasks/T-<spec>.md in-progress done
```

Completion is reported via terminal output — the parent session reads stdout for the eval pass/fail summary and the final `transition-status.sh` confirmation line.

---

## Failure modes

| Symptom | Action |
|---------|--------|
| Claude claims done but evals fail when re-run | Treat as defect; revert diff with `git checkout -- .`; re-dispatch with the eval failure log appended to the prompt |
| Claude edits outside `touches_paths` | Discard the offending hunks via `git checkout -p`; re-dispatch with a tighter prompt citing the do-not-touch list |
| Subagent stalls without status flip | Parent session times out; manually transition `in-progress -> parked` and record `blocked_reason: subagent-timeout` |
| Agent refuses task citing safety | Inspect spec for ambiguous instructions; the contract should never require unsafe action — re-author |

---

## See also

- [../dispatching-a-task-spec.md](../dispatching-a-task-spec.md) — router and pre-flight checklist
- [../../references/concepts/agent-contract.md](../../references/concepts/agent-contract.md) — read-zone semantics
- [../../references/concepts/signed-off.md](../../references/concepts/signed-off.md) — autonomy contract
- [kimi.md](kimi.md) — Kimi CLI alternative (often invoked from Claude itself)
