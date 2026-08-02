# Dispatch Recipe: Gemini (generic LLM CLI)

> **Use when:** `execution_backend: gemini` or any generic completion-API CLI — the path for engines that lack a purpose-built broker. Treat the spec as a prompt body and map text responses back to `status:` flips manually.

This recipe documents the **generic LLM CLI** pattern. The same shape works for any completion-API tool (`gemini-cli`, `ollama run`, `llm` from Simon Willison, `aichat`). Substitute the CLI name; the contract is identical.

---

## Prerequisites

- A completion-API CLI installed (e.g. `gemini` from `gemini-cli`, `llm`, `ollama`).
- API key or local model available; `gemini --version` (or equivalent) confirms install.
- Spec is at `signed_off: true` with the gate clean.
- Working tree clean — generic CLIs do not enforce origin-state checks.
- A wrapper script (or shell function) that pipes the spec body into the CLI and applies the resulting diff. There is no broker doing this for you.

---

## Dispatch command

The canonical pattern feeds the spec into the model with a system prompt that names the agent contract:

```bash
gemini chat \
  --system "You are an autonomous executor. Honor signed_off:true. Stay within touches_paths. Emit only a unified diff." \
  --file tasks/T-<spec>.md \
  > /tmp/T-<spec>.diff

git apply --check /tmp/T-<spec>.diff && git apply /tmp/T-<spec>.diff
```

For tools that stream responses, capture the diff block out of the streamed output, then apply it the same way. The dispatcher is responsible for everything the Kimi broker does for free.

---

## Status reporting

Generic CLIs never flip `status:`. The dispatcher must do it after each phase:

```bash
bash .claude/skills/task-spec/scripts/transition-status.sh \
  tasks/T-<spec>.md ready in-progress

# ... run gemini, apply diff, run evals ...

if bash .claude/skills/task-spec/scripts/safe-to-delegate.sh tasks/T-<spec>.md; then
  bash .claude/skills/task-spec/scripts/transition-status.sh \
    tasks/T-<spec>.md in-progress done
else
  bash .claude/skills/task-spec/scripts/transition-status.sh \
    tasks/T-<spec>.md in-progress parked
fi
```

---

## Failure modes

| Symptom | Action |
|---------|--------|
| Model returns prose, not a diff | Strengthen system prompt; require the response to start with `diff --git`; reject and retry |
| `git apply --check` fails | Model produced an invalid patch; retry with `--3way` or fall back to manual review |
| Model edits files outside `touches_paths` | Generic CLIs lack sandboxing; the dispatcher must filter the diff before applying |
| API quota exhausted mid-task | Park the task with `blocked_reason: api-quota`; resume after quota refresh |
| Local model hallucinates the spec is already done | Run `safe-to-delegate.sh` to corroborate; if evals fail, treat as defect and re-dispatch |

---

## See also

- [../dispatching-a-task-spec.md](../dispatching-a-task-spec.md) — router and pre-flight checklist
- [custom.md](custom.md) — for fully custom dispatch (templated wrapper)
- [claude-code.md](claude-code.md) — when a broker-managed path is available
- [../../references/concepts/agent-contract.md](../../references/concepts/agent-contract.md) — what the system prompt must reference
