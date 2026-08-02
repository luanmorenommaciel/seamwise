# Dispatch Recipe: Codex CLI

> **Use when:** `execution_backend: codex` — hand the spec to the OpenAI Codex CLI (or its Claude Code plugin sibling) for autonomous execution.

Codex consumes the spec via its CLI front-end and honors a `backend_metadata:` block in the frontmatter when present (e.g. a `codex:` sub-map naming model, sandbox profile, approval mode). The CLI surfaces exit codes the dispatcher must respect.

---

## Prerequisites

- `codex` CLI installed and on PATH (verify with `codex --version`).
- Codex auth completed (`codex login` or `OPENAI_API_KEY` exported).
- Spec is at `signed_off: true` with the gate clean.
- Optional but recommended: a `backend_metadata:` block in the spec frontmatter (e.g. a `codex:` sub-map naming `model`, `sandbox`, and `approval_mode`). Absent it, Codex applies its installed defaults.
- Working tree is clean so the diff is attributable.

---

## Dispatch command

The non-interactive form is `codex exec [OPTIONS] [PROMPT]` (alias `codex e`). The PROMPT is read from the argument or from stdin — there is no task-file flag, so pass the spec body (or a derived instruction) as the prompt. Verified against codex-cli 0.133.0 (`codex exec --help`):

```bash
codex exec --cd "$(pwd)" --sandbox workspace-write --skip-git-repo-check \
  "$(cat tasks/T-<spec>.md)"
```

Passing the raw spec works, but a derived prompt that names the contract is more reliable — tell Codex to read the spec, implement only the files in `touches_paths`, and run the Exit Check before returning:

```bash
codex exec --cd "$(pwd)" --sandbox workspace-write --skip-git-repo-check \
  "Read tasks/T-<spec>.md. Implement only the files listed under touches_paths, then run the spec's Exit Check and report the result."
```

Common flag overrides (consult `codex exec --help` for your version): `-m/--model <MODEL>` selects the model, `-s/--sandbox <read-only|workspace-write|danger-full-access>` sets the sandbox policy, `-C/--cd <DIR>` sets the working root, and `--skip-git-repo-check` allows running outside a Git repo. For fully unattended runs that must skip every confirmation, `--dangerously-bypass-approvals-and-sandbox` replaces interactive approval (use only inside an externally sandboxed environment):

```bash
codex exec --cd "$(pwd)" --model gpt-5-codex --sandbox workspace-write \
  --skip-git-repo-check "$(cat tasks/T-<spec>.md)"
```

The `backend_metadata:` block (when present) supplies these values so the dispatcher does not have to repeat them on the command line.

---

## Status reporting

Codex does not flip `status:` automatically. After the CLI returns:

```bash
test $? -eq 0 && bash .claude/skills/task-spec/scripts/transition-status.sh \
  tasks/T-<spec>.md in-progress done
```

For wraparound automation, wrap the dispatch in a shell function that flips `ready -> in-progress` before the call and `in-progress -> done|parked` based on `$?`.

---

## Failure modes

`codex exec` does not publish a stable exit-code contract, so DO NOT branch on
specific codes — treat the outcome as **zero (ran) vs non-zero (failed to run)**
and let `accept-task.sh` be the source of truth for whether the work is real.
For more detail on a run, re-invoke with `--json` (JSONL events to stdout) or
`-o/--output-last-message <FILE>` (capture the final assistant message).

| Outcome | Meaning | Action |
|---------|---------|--------|
| exit 0 | Codex ran to completion | Run `accept-task.sh --stamp` — the acceptance gate (not the exit code) decides done |
| non-zero exit | Codex could not complete (failure, denied action, or timeout) | Re-run with `--json` to inspect events; if a needed write was denied, ensure `--sandbox workspace-write` and that `touches_paths` covers the files |
| exit 0 but `accept-task.sh` REJECTs | Engine claimed completion but evals fail / blast-radius breached | Treat as defect — revert the diff and re-dispatch with the eval log in the prompt |

---

## See also

- [../dispatching-a-task-spec.md](../dispatching-a-task-spec.md) — router and pre-flight checklist
- [claude-code.md](claude-code.md) — alternative when no Codex auth is available
- [../../references/concepts/agent-contract.md](../../references/concepts/agent-contract.md) — read-zone semantics Codex honors
- [custom.md](custom.md) — for non-standard Codex deployments (e.g. self-hosted)
