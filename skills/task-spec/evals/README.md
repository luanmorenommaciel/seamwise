# task-spec — evals

`evals.json` holds 6 task-benchmark cases (prompt + expectations) that exercise the
crown jewels: the 6 zones, the behavior-to-eval traceability chain, runnable bash
evals (the moat), the six-tier effort gate (XL/XXL decompose into children), the closed loop
(validate → safe-to-delegate), and vendor-neutral frontmatter. Grounded in this
repo's postgres → duckdb → dbt → MCP stack.

## Running the benchmark

Use the bundled skill-creator machinery from the repo root:

```bash
# trigger eval (does the description fire the skill?) — needs a trigger-set array
python -m scripts.run_eval --eval-set <trigger-set.json> \
  --skill-path .claude/skills/task-spec --runs-per-query 3
```

## Known limitation — headless trigger detection (2026-07)

`run_eval.py` detects a "trigger" by watching `claude -p`'s stream-JSON for a
`Skill`/`Read` tool-use event. In this environment (Claude Code 2.1.191, headless
`claude -p`), that detector reported **0% across every query — positives and
negatives alike**, including a query that literally says "create a task-spec."

A direct probe proved this is a **detector false-negative, not a skill problem**:
running `claude -p "Create a task-spec ..."` and inspecting the raw stream shows the
model **does invoke the Skill tool** (`tool_uses seen: ['Skill', 'Skill', ...]`).
The skill triggers correctly; the harness's stream-event matcher just doesn't
recognize this Claude Code version's event shape.

**Consequence:** the with/without-skill pass-rate benchmark and the automatic
`improve_description.py` pass cannot produce trustworthy signal here — feeding the
improver all-zeros would optimize against noise and risk stripping the
crown-jewel-precise language.

**What we did instead:** the description was tuned **by hand** against Anthropic's
"Complete Guide to Building Skills" — front-loading the literal trigger phrases a
user says ("create a task", "make this executable", "decompose this into work")
while preserving every crown jewel (Task-Spec v3, PRD + Given/When/Then behavior +
runnable bash evals, the behavior-to-eval traceability chain, the post-execution
acceptance gate, and the S/M-vs-L/XL effort routing) and adding a negative boundary
(routes L/XL / subjective work to SDD) to prevent over-triggering.

Re-run the live benchmark in an **interactive** session (where skill-load events
surface normally) to get real trigger/pass-rate numbers.
