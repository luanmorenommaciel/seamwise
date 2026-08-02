# Runbook: Convert Legacy Task to Task-Spec v3

> **Use when:** A pre-Task-Spec markdown task exists and needs upgrading to v2.1.

## Inputs

- Existing T-*.md or similar task doc
- Goal: produce a v1-compliant version

## Most legacy tasks have ~60% of v1 already

Existing patterns that map directly:

| Legacy section | Maps to v1 zone |
|----------------|-----------------|
| Goal / Objective | Zone 1 — Goal |
| Background / Context | Zone 1 — Context |
| Success criteria (prose checklist) | Zone 2 — needs conversion to runnable bash |
| Implementation steps | (informative; not required in v1) |
| Anti-patterns / Don'ts | Zone 3 — Anti-Patterns |
| Do-not-touch / Out-of-scope | Zone 3 — Do-Not-Touch |
| Exit check | Zone 2 — Exit Check (often already bash) |
| Open questions | Zone 4 — Open Questions |

## What usually needs adding

1. **YAML frontmatter** — many legacy tasks lack structured frontmatter
2. **Runnable bash evals** — prose success criteria need conversion
3. **Validation card YAML** — usually absent
4. **Effort gate validation** — confirm the tier: a runnable leaf (XS/S/M/L) within its write-surface budget, or a node (XL/XXL) with a `children:` block

## Conversion workflow

### Step 1 — Read and audit

```bash
# Identify which v1 elements are present
grep -E '^(##|---)' tasks/legacy-task.md
```

### Step 2 — Map legacy sections to v1 zones

Manually annotate which section becomes which zone.

### Step 3 — Convert prose success criteria to bash

```text
Legacy:
- [ ] Docker stack reaches healthy state
- [ ] UI loads at localhost:3000
- [ ] At least one trace visible in UI

v1:
eval_1() { docker ps --filter 'name=langfuse' --filter 'health=healthy' | grep -q langfuse; }
eval_2() { curl -fs http://localhost:3000/api/public/health | jq -e '.status == "OK"'; }
eval_3() { scripts/check_trace_visible.sh; }
```

### Step 4 — Add validation card YAML

Mirror the bash evals into YAML form.

### Step 5 — Generate the v1 file

```bash
bash ~/.claude/skills/task-spec/scripts/generate-task-spec.sh \
    <slug> <effort> <agent> <original-source-note>
```

Then fill zones with mapped content + new evals.

### Step 6 — Side-by-side audit

Compare legacy and v1. Confirm:
- Nothing lost
- New evals catch what the prose checklist asked for
- Validation passes

### Step 7 — Archive the legacy

Move the legacy task to a `tasks/_legacy/` folder or git history. Keep v1 as canonical.

## Example

Legacy: `tasks/T-20260504-langfuse-verify.md` (already nearly v1-shaped — see the existing task file).

Conversion takes ~15 minutes per legacy task because most content survives intact.
