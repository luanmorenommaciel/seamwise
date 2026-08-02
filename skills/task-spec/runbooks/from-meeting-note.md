# Runbook: From Meeting Note to Task-Specs

> **Use when:** A meeting note has action items that need to become backlog tasks.

## Inputs

- Meeting note file (Markdown, often from `/meeting` command + Krisp MCP)
- Optional: which AI items to extract (default: all)

## Workflow

### Step 1 — Read the meeting note

Look for action items (often "AI #N" or numbered lists under "Action Items").

```bash
grep -A 3 -E '^(AI #|[0-9]+\.) ' notes/2026-05-04-handoff.md
```

### Step 2 — One task per action item

For each AI:

1. Extract the action verb + object → becomes the title
2. Estimate effort (leaf XS/S/M/L; XL/XXL → decompose into a node + children)
3. Identify touches_paths from context
4. Set `source_note: <meeting note path>`
5. Set `source_action_item: "AI #N — <description>"`

### Step 3 — MCP research per task

Each task gets its own MCP query cycle. Don't reuse research across tasks; each task's anti-patterns are domain-specific.

### Step 4 — Generate each task

```bash
for AI in "AI #1" "AI #2" "AI #6"; do
  bash ~/.claude/skills/task-spec/scripts/generate-task-spec.sh \
      "<slug-for-AI>" S any "notes/2026-05-04-handoff.md"
  # then fill in zones
done
```

### Step 5 — Cross-link dependencies

If AI #6 depends on AI #3, set in frontmatter:

```yaml
depends_on: [T-20260519-ai-3-slug]
```

### Step 6 — Bulk validate

```bash
for f in tasks/T-20260519-*.md; do
  bash ~/.claude/skills/task-spec/scripts/validate-task-spec.sh "$f"
done
```

## Example

Meeting note has:
- AI #1: "Verify Langfuse stack works end-to-end"
- AI #2: "Confirm OTEL traces include session.id"
- AI #6: "Update ADF parser for 2.56 spec extension records"

Produces:
- `T-20260504-langfuse-verify.md` (depends_on: [])
- `T-20260504-otel-verify.md` (depends_on: [T-20260504-langfuse-verify])
- `T-20260511-ingest-adf-256-extension-records.md` (depends_on: [], precondition: spec ready)

Each carries `source_action_item: "AI #N — ..."` for provenance.
