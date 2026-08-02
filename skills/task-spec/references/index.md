# Task-Spec Knowledge Base

> **Purpose**: KB for the `task-spec` skill — the format, methodology, and patterns.
> **Owner Skill**: `~/.claude/skills/task-spec/`
> **Owner Agent**: `~/.claude/agents/task-architect.md`
> **MCP Validated**: 2026-05-19

---

## Concepts (≤150 lines each)

| File | Purpose |
|------|---------|
| [concepts/task-spec-v1.md](concepts/task-spec-v1.md) | **THE format spec** (citable, portable, complete) |
| [concepts/eval-driven-development.md](concepts/eval-driven-development.md) | EDD methodology |
| [concepts/edd-vs-sdd-honest-comparison.md](concepts/edd-vs-sdd-honest-comparison.md) | When to use which |
| [concepts/six-zones.md](concepts/six-zones.md) | File anatomy |
| [concepts/profiles.md](concepts/profiles.md) | **v3** effort-scaled profiles (lite/standard/full) + the behavior↔eval traceability rule |
| [concepts/conformance-levels.md](concepts/conformance-levels.md) | **v3** executor conformance L0/L1/L2 + the A2A lifecycle mapping |
| [concepts/decomposition.md](concepts/decomposition.md) | **v3** intent/PRD → N atoms: the flat index+detail shape, holes-as-blockers, profile-per-atom, `depends_on`/`parent` edges |
| [concepts/effort-gate.md](concepts/effort-gate.md) | S/M/L/XL routing rules |
| [concepts/agent-contract.md](concepts/agent-contract.md) | Cross-vendor contract |
| [concepts/signed-off.md](concepts/signed-off.md) | **The autonomy contract** — who produces `signed_off: true`, what it asserts, why hand-stamping is forbidden |
| [concepts/backlog-architecture.md](concepts/backlog-architecture.md) | 5-layer state management |

## Patterns (≤200 lines each)

| File | Purpose |
|------|---------|
| [patterns/runnable-bash-evals.md](patterns/runnable-bash-evals.md) | Writing terminal, idempotent evals |
| [patterns/validation-card-yaml.md](patterns/validation-card-yaml.md) | The YAML contract mirror |
| [patterns/atomic-status-transitions.md](patterns/atomic-status-transitions.md) | The 7-step transition protocol |
| [patterns/anti-patterns-extraction.md](patterns/anti-patterns-extraction.md) | Mining Zone 3 from MCP research |
| [patterns/do-not-touch-detection.md](patterns/do-not-touch-detection.md) | Repo-scan patterns |

## Quick Reference

| File | Purpose |
|------|---------|
| [quick-reference.md](quick-reference.md) | One-page cheatsheet |

## Runbooks (in `../runbooks/`)

| File | Purpose |
|------|---------|
| [../runbooks/first-spec-walkthrough.md](../runbooks/first-spec-walkthrough.md) | **Your first 10 minutes** — install → generate → validate → gate end-to-end |
| [../runbooks/from-fuzzy-intent.md](../runbooks/from-fuzzy-intent.md) | Paragraph → Task-Spec |
| [../runbooks/decomposing-intent.md](../runbooks/decomposing-intent.md) | **Intent / PRD / set-of-calls → N linked atomic specs** — flat index + detail atoms, `depends_on` edges, holes-as-blockers |
| [../runbooks/from-meeting-note.md](../runbooks/from-meeting-note.md) | Krisp output → Task-Spec |
| [../runbooks/from-existing-task.md](../runbooks/from-existing-task.md) | Legacy → v2.1 conversion |
| [../runbooks/validating-a-task-spec.md](../runbooks/validating-a-task-spec.md) | Pre-gate structural linter walkthrough |
| [../runbooks/dispatching-a-task-spec.md](../runbooks/dispatching-a-task-spec.md) | **What to do after `safe-to-delegate.sh --stamp`** — router to per-engine recipes |
| [../runbooks/recovering-from-crash.md](../runbooks/recovering-from-crash.md) | State recovery |
| [../runbooks/empirical-experiment-protocol.md](../runbooks/empirical-experiment-protocol.md) | SDD vs EDD experiment |

## Dispatch Recipes (in `../runbooks/dispatch-recipes/`)

Per-engine recipes routed from `dispatching-a-task-spec.md`. Each follows the same five-section shape: Prerequisites / Dispatch command / Status reporting / Failure modes / See also.

| File | Engine |
|------|--------|
| [../runbooks/dispatch-recipes/claude-code.md](../runbooks/dispatch-recipes/claude-code.md) | Claude Code (Task() tool, subagent delegation) |
| [../runbooks/dispatch-recipes/codex.md](../runbooks/dispatch-recipes/codex.md) | Codex CLI (`codex run --task ...`) |
| [../runbooks/dispatch-recipes/kimi.md](../runbooks/dispatch-recipes/kimi.md) | Kimi CLI via the 12-stage broker pipeline |
| [../runbooks/dispatch-recipes/gemini.md](../runbooks/dispatch-recipes/gemini.md) | Gemini / generic completion-API CLIs |
| [../runbooks/dispatch-recipes/taskship.md](../runbooks/dispatch-recipes/taskship.md) | taskship runtime |
| [../runbooks/dispatch-recipes/anthive.md](../runbooks/dispatch-recipes/anthive.md) | anthive parallel-session dispatch |
| [../runbooks/dispatch-recipes/custom.md](../runbooks/dispatch-recipes/custom.md) | DIY escape hatch (v2.2 `dispatch_recipe:` field) |

---

## How the agent navigates this KB

The `task-architect` agent reads from this folder:

1. **Start with** `concepts/task-spec-v1.md` for the format reference
2. **Concepts** for definitional questions ("what IS an effort gate?")
3. **Patterns** for implementation questions ("how do I write an idempotent eval?")
4. **Runbooks** for workflow questions ("how do I convert a meeting note?")

Cross-link with `[[concept-name]]` syntax. Validate against Context7 MCP at runtime.
