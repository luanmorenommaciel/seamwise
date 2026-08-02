# Runbook: Batch Sprint Compose

> **Use when:** you have a structured list of 3–20 atomic tasks in a known domain
> and need to produce Task-Spec stubs fast. You already know the codebase, so MCP
> research (Phase 2) and task-architect judgment (Phase 4) add overhead without
> value.

## Inputs

- A text file with one intent per line in `slug: description` form
- Effort class (leaf tier XS/S/M/L) — applies to every generated leaf spec
- (optional) `--agent` hint, `--source-note` path, `--queue` flag

## Pre-condition: verify Fast Batch is appropriate

Run this checklist. If ≥ 4 items are true, use Fast Batch. Otherwise, run the
[full From-Fuzzy-Intent workflow](./from-fuzzy-intent.md) on the first spec to
prove the pattern, then batch the rest.

| # | Check | Your answer |
|---|-------|-------------|
| 1 | You already understand the codebase and conventions | ☐ yes ☐ no |
| 2 | No external library docs are needed (no Context7/Exa/Ref value) | ☐ yes ☐ no |
| 3 | Each task can be expressed as `slug: one-line description` | ☐ yes ☐ no |
| 4 | You need 3 or more specs at once | ☐ yes ☐ no |
| 5 | You can provide `touches_paths` and draft evals without agent help | ☐ yes ☐ no |
| 6 | A prior similar batch validated first-try | ☐ yes ☐ no |

## Step-by-step

### 1. Prepare the intent file

Create a file (e.g. `intents.txt`) with one line per task:

```text
# Comments and blank lines are ignored
fix-login-redirect:   Redirect to /dashboard after OAuth success instead of /
add-rate-limiting:    Add 100 req/min rate limit to /api/v1/analyze endpoint
update-telemetry:     Emit batch-completed event to Langfuse after each sprint
```

Rules:
- **Slug** must be kebab-case (`[a-z0-9]+(-[a-z0-9]+)*`)
- **Description** becomes the task title (improve it later if needed)
- Lines without a colon are skipped with a warning

### 2. Generate stubs

```bash
bash ~/.claude/skills/task-spec/scripts/batch-generate.sh \
    --intent-file intents.txt \
    --effort S \
    --agent any \
    --source-note docs/audit/2026-05-27-review.md \
    --queue
```

Flags reference:

| Flag | Required | Description |
|------|----------|-------------|
| `--intent-file <path>` | **yes** | Path to the intent list file |
| `--effort S\|M` | **yes** | Effort class for every spec |
| `--agent <name>` | no | Agent hint (default: `any`) |
| `--source-note <path>` | no | Provenance applied to every spec |
| `--queue` | no | Write to `tasks/queue/` instead of `tasks/` |
| `--dry-run` | no | Preview what would be created without writing |
| `--skip-validation` | no | Skip the bulk validation pass |
| `--validate-opts <opts>` | no | Extra flags for `validate-task-spec.sh` (e.g. `--skip-touches-paths`) |

### 3. Fill the stubs

Each generated file has `{{TODO}}` placeholders. Edit every file:

| Zone | What to fill |
|------|--------------|
| Frontmatter | `title` (already filled from description), `touches_paths`, `tags` |
| Why / Goal / Context | Lean prose; link to existing docs or audit notes |
| Success Criteria | 3+ `eval_N()` bash functions — the most important part |
| Validation Card | Update `expected_duration_sec`, `budget_iterations` if not 15 |
| Exit Check | Must call every `eval_N()` defined |
| Rollback Plan | `(none)` if append-only, otherwise specific steps |
| Observability Hooks | `(none)` if not applicable |
| Anti-Patterns | 2–3 bullets mined from prior failures in this domain |
| Do-Not-Touch | Exact paths the executor must not modify |
| Open Questions | `(none — fully specified)` if nothing remains |

**Tip:** open all generated files in your editor and use multi-cursor or a
snippet to fill common fields (e.g. `tags: [batch-sprint]`, shared
`do-not-touch` list).

### 4. Bulk-validate

If you used `--skip-validation` during generation, run it now:

```bash
for f in tasks/queue/T-*.md; do
  bash ~/.claude/skills/task-spec/scripts/validate-task-spec.sh "$f"
done
```

Or validate a single file:

```bash
bash ~/.claude/skills/task-spec/scripts/validate-task-spec.sh \
    --shellcheck-evals \
    tasks/queue/T-20260527-fix-login-redirect.md
```

### 5. Commit

```bash
git add tasks/queue/ tasks/_state.yaml tasks/_metrics.jsonl
git commit -m "task: batch sprint compose — N specs from audit"
```

## Example walkthrough

**Context:** An audit identified 11 skill-improvement tasks in a known repo.
The domain (task-spec skill files) is fully understood; no MCP research is needed.

| Step | Action | Result |
|------|--------|--------|
| Prepare | Wrote `intents.txt` with 11 `slug: description` lines | 11 intents |
| Generate | Ran `batch-generate.sh --intent-file intents.txt --effort S --queue` | 11 stub files in `tasks/queue/` |
| Fill | Edited titles, `touches_paths`, evals, anti-patterns per file | All stubs complete |
| Validate | Bulk validation passed on every file | 0 failures |
| Commit | `git add tasks/queue/` + commit | Clean state |

Total time: ~20 min for 11 specs (vs. ~4 hours if each ran the full 6-phase workflow).

## When NOT to use this runbook

- The task domain is unfamiliar → use [from-fuzzy-intent.md](./from-fuzzy-intent.md)
- You only need 1–2 specs → use [from-fuzzy-intent.md](./from-fuzzy-intent.md)
- The user intent is a paragraph, not a structured list → use [from-fuzzy-intent.md](./from-fuzzy-intent.md)
- You need the agent to draft evals or research failure modes → use [from-fuzzy-intent.md](./from-fuzzy-intent.md)
- Effort is XL or XXL → it's a decomposition NODE: emit a parent + a `children:` block of leaf specs (no route out)

## Remember

> **"Batch compose is fast because you're reusing context, not because you're
> skipping quality."**
>
> Every spec still needs 3+ evals, a validation card, an exit check, and a clean
> validation pass. The speed comes from eliminating the MCP round-trips and
> agent-spawn overhead, not from cutting corners on the spec itself.
