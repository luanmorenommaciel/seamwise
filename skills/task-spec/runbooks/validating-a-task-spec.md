# Runbook: Validating a Task-Spec

> **Use when:** Confirming a T-*.md is v3.1-compliant before commit or dispatch.

## The validator

```bash
bash ~/.claude/skills/task-spec/scripts/validate-task-spec.sh tasks/T-XXX.md
```

Exit codes:
- 0 — valid (or accepted with warnings: legacy v0/v1, or non-fatal warnings)
- non-zero (1) — invalid: any structural error fails the spec

The validator's success path exits 0 and its failure path exits 1 — there is no distinct exit code per failure class. (The script's header comment lists 2/3 for invalid-values / leftover-placeholders, but the reporting logic emits a single `exit 1` for every error category; do not branch on 2 or 3.) Read the printed `FAIL:` lines for the specific cause.

## What it checks

**Irreducible core (every profile, every non-v0 version):** `## Goal` + `## Success Criteria` (≥1 `eval_N()` bash function) + `## Validation Card` + `## Exit Check`. That is the minimal self-verifying unit — `## Validation Card` and `## Exit Check` are required even for `lite` (validator Check 6).

**Profile-scaled additions** (the `profile:` field — `lite` | `standard` | `full` — scales which zones are *required* to the effort/blast-radius; absent → `standard`):

- `standard` and `full` additionally require `## Context`, `## Anti-Patterns`, `## Do-Not-Touch`, and `## Open Questions`. `lite` omits these (it earns the smaller surface by declaring `profile: lite`).
- **`## Behavior`** (Given/When/Then `B-N` scenarios) is required for **v3 `standard`/`full`** — it is the BDD layer and the traceability anchor. Optional for `lite`; never required for v2/v1/v0.
- `## Rollback Plan` + `## Observability Hooks` are required for `full`, recommended (warning only) otherwise.

**Mechanical field checks:**

1. YAML frontmatter exists and has all required fields
2. `effort` is `S` or `M` (rejects L/XL)
3. `status` is one of: ready/in-progress/blocked/done/parked
4. `id` matches `T-YYYYMMDD-<kebab-slug>` format and equals the filename basename
5. Validation Card YAML has `success_criteria` + `retry_policy` + `agent_contract` (v2/v3 agent_contract: `version: 2`)
6. No leftover `{{TODO}}` or `{{PLACEHOLDER}}` strings; no inverted-grep-c eval foot-guns
7. **`verifies:` traceability (v3 `standard`/`full`):** every `## Behavior` `B-N` must be verified by ≥1 eval (no orphan behavior), and every eval's `verifies:` must reference a declared `B-N` (no dangling reference)
8. Sign-off / acceptance envelope floors: a hand-set `signed_off: true` or `accepted: true` (missing `_by`/`_at`) is rejected — those envelopes are produced only by `safe-to-delegate.sh --stamp` and `accept-task.sh` respectively

Profiles are the source of truth for which zones are required — see [../references/concepts/profiles.md](../references/concepts/profiles.md).

## When validation fails

| Failure | Fix |
|---------|-----|
| Missing frontmatter field | Add to YAML at top of file |
| Effort is XL/XXL | It's a NODE — decompose into a `children:` block of leaf tasks (XS/S/M/L). No route out. |
| Missing zone | Add the section header + content |
| No eval_N() functions | Write at least 3 runnable bash evals |
| Validation Card YAML missing | Add the YAML block under `## Validation Card` |
| Leftover `{{TODO}}` | Fill in the stub content |

## Pre-commit hook (optional)

Add to `.git/hooks/pre-commit`:

```bash
#!/usr/bin/env bash
# Validate any modified Task-Spec files
CHANGED=$(git diff --cached --name-only --diff-filter=ACM | grep '^tasks/T-.*\.md$' || true)
for f in $CHANGED; do
  bash ~/.claude/skills/task-spec/scripts/validate-task-spec.sh "$f" || exit 1
done
```

Prevents bad Task-Specs from entering git history.

## Bulk validation

```bash
# Validate every Task-Spec in the backlog
find tasks -name 'T-*.md' -exec \
  bash ~/.claude/skills/task-spec/scripts/validate-task-spec.sh {} \;
```

Useful before opening a PR with many task additions.
