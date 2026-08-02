# Dispatch Recipe: Custom engine (DIY escape hatch)

> **Use when:** None of the named executors fit — you're integrating with a bespoke runtime, a self-hosted model gateway, an MCP server, or an in-house agentic system. This is the escape hatch.

A `signed_off: true` spec is a portable contract. Any process that can read markdown, honor `agent_contract`, run bash evals, and flip `status:` can execute it. This recipe documents the minimum interface a custom engine must implement.

---

## Prerequisites

- A clear understanding of the four contract surfaces the engine must respect:
  1. **Read-zone honoring** — only read files listed in `agent_contract.read`.
  2. **Write-path discipline** — only modify files listed in `touches_paths` / `creates_paths`.
  3. **Eval execution** — run every `eval_N` block; do not claim done unless all pass.
  4. **Status discipline** — flip `status:` only via `transition-status.sh`.
- v2.2 of the Task-Spec format introduces a deferred `dispatch_recipe:` frontmatter field that names this recipe file directly. Until then, the engine binding is implicit via `execution_backend: custom`.
- Working tree clean; spec at `signed_off: true`.

---

## Dispatch command

There is no canonical command — that is the point. The recommended shape is a wrapper script in `scripts/` that:

```bash
#!/usr/bin/env bash
SPEC="$1"
my-custom-engine \
  --spec "$SPEC" \
  --read-zones "$(yq '.agent_contract.read[]' "$SPEC")" \
  --write-paths "$(yq '.touches_paths[] // .creates_paths[]' "$SPEC")" \
  --post-eval "bash .claude/skills/task-spec/scripts/safe-to-delegate.sh $SPEC"
```

When v2.2 ships, the dispatcher will read `dispatch_recipe: dispatch-recipes/my-engine.md` from the frontmatter and invoke the recipe automatically.

---

## Status reporting

Custom engines must flip `status:` via the canonical script — no exceptions:

```bash
bash .claude/skills/task-spec/scripts/transition-status.sh \
  tasks/T-<spec>.md ready in-progress

# ... custom execution ...

bash .claude/skills/task-spec/scripts/transition-status.sh \
  tasks/T-<spec>.md in-progress done
```

If the engine cannot call shell scripts, expose an HTTP endpoint that wraps `transition-status.sh` and have the engine POST status changes. The status field itself is the source of truth; the path to flipping it is engine-specific.

---

## Failure modes

| Symptom | Action |
|---------|--------|
| Engine writes outside declared paths | Treat as contract violation; revert all changes and re-author the spec with tighter `touches_paths` |
| Engine skips eval execution | Wrap dispatch in a post-run gate: re-run `safe-to-delegate.sh` and treat eval failure as a defect |
| Engine flips `status:` without `transition-status.sh` | The audit envelope will reject it on next validation — fix the engine to use the canonical script |
| v2.2 `dispatch_recipe:` field ignored | You're on v2.1 — wire the recipe path manually via your wrapper script |
| No path back to a supported engine | Document the bespoke recipe under `dispatch-recipes/<engine>.md` so the next operator can re-dispatch |

---

## See also

- [../dispatching-a-task-spec.md](../dispatching-a-task-spec.md) — router and pre-flight checklist
- [gemini.md](gemini.md) — closest sibling for generic completion-API engines
- [../../references/concepts/agent-contract.md](../../references/concepts/agent-contract.md) — the contract every engine must honor
- [../../references/concepts/signed-off.md](../../references/concepts/signed-off.md) — autonomy contract
