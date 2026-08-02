# Runbook: From Fuzzy Intent to Task-Spec

> **Use when:** user has a paragraph of intent ("verify our deploy pipeline works"). No existing structure.

## Inputs

- User's natural-language intent (1-3 sentences)
- (optional) source_note path

## Phase-by-phase

### Phase 1 — Clarify (≤1 round-trip)

If the intent is unparseable, ASK ONCE:
- "What's the success signal? How would you know it worked?"
- "Is this S (one day) or M (1-3 days) of work?"
- "Any specific files involved?"

Don't ask more than once. If still vague, the task isn't ready — defer.

### Phase 2 — MCP research

- Context7: any tools/libraries mentioned? Fetch current docs.
- Exa: search "<domain> <verb> production 2026" for examples.
- Note common failure modes — these become Zone 3 anti-patterns.

### Phase 3 — Repo scan

- Glob for files matching the intent's domain
- Read CLAUDE.md for project conventions
- Identify do-not-touch zones (auto-gen, sibling modules)

### Phase 4 — Architect (spawn task-architect)

Pass: intent + research findings + repo scan.
Returns: classified effort, draft evals, anti-patterns, do-not-touch.

### Phase 5 — Compose

```bash
bash ~/.claude/skills/task-spec/scripts/generate-task-spec.sh \
    <slug> <effort> <agent> <source_note>
```

Then edit the generated file to fill in:
- title, why, goal, context
- evals (from agent's draft)
- validation card YAML
- exit check
- anti-patterns (from agent's research)
- do-not-touch (from repo scan)
- open questions (from agent's uncertainty list)

### Phase 6 — Validate

```bash
bash ~/.claude/skills/task-spec/scripts/validate-task-spec.sh tasks/T-*.md
```

Must pass before commit.

## Example walkthrough

Intent: "Verify our Langfuse self-hosted stack ingests OTEL traces from our agent runs."

| Phase | Result |
|-------|--------|
| Clarify | "Success = a real trace appears in Langfuse UI with session.id attribute." S effort. |
| MCP research | Context7: v3 OTEL endpoint is `/api/public/otel/v1/traces`. Exa: forgetting resource attributes is the #1 failure mode. |
| Repo scan | `docker/langfuse-compose.yml` exists; `anthive/observability.py` exists. |
| Architect | Effort=S, agent=python-developer, 4 evals drafted. |
| Compose | Generated `tasks/T-20260519-verify-langfuse-otel.md` |
| Validate | All checks pass |

Total time: 15-30 min depending on MCP latency.
