# Runbook: SDD vs EDD Empirical Experiment

> **Purpose:** Run a rigorous head-to-head test of SDD vs EDD on real tasks.
> Pre-registered hypotheses + falsifiable outcomes = publishable result.

## The protocol

### Phase 0 — Pre-register hypotheses (BEFORE writing tasks)

Commit `experiment/HYPOTHESES.md` to git with predictions before authoring anything.

```markdown
# Pre-registered Hypotheses
Date: YYYY-MM-DD (committed before any experiment work)

H1: EDD time-to-done ≤ SDD on 7+/10 tasks (confidence: 65%)
H2: EDD iterations > SDD (more cheap loops vs few expensive reviews) (80%)
H3: EDD reopen rate < SDD on 7+/10 tasks (70%)
H4: EDD token cost HIGHER than SDD (more retries) (60%)
H5: EDD cross-vendor pass rate > SDD (85%)
H6: EDD authoring time HIGHER than SDD (75%)
H7: EDD catches injected ambiguities at higher rate (70%)
H8: Overall: EDD wins on ≥5/8 metrics across ≥7/10 tasks (50%)
```

Pre-registration prevents post-hoc rationalization.

### Phase 1 — Pick 10 real tasks

Sources:
- Existing `tasks/` backlog (real work)
- Recent meeting note action items
- Audit findings
- Backlog from `/meeting`

Criteria: S or M effort, machine-checkable success, no subjective requirements.

### Phase 2 — Author each twice

For each of 10 tasks:

```text
experiment/
├── sdd/
│   └── T-XXX.md     ← AgentSpec /define output (5-phase SDD spec)
└── edd/
    └── T-XXX.md     ← Task-Spec v3 output (with runnable evals)
```

Same task, two formats. Don't peek at one while writing the other.

### Phase 3 — Execute each twice

```bash
# SDD execution
cd /tmp/sdd-run
/agentspec:build T-XXX
# capture: time, tokens, iterations, reopens

# EDD execution
cd /tmp/edd-run
# read experiment/edd/T-XXX.md
# run eval loop until pass or budget exhausted
```

Same agent (e.g., Claude Opus 4.7) for both. Same hardware. Different methodology only.

### Phase 4 — Measure 8 metrics

| Metric | How |
|--------|-----|
| Time-to-done | Wall clock |
| Iterations | Count from `_metrics.jsonl` or session log |
| Reopens (7 days) | Did anyone reopen the task within a week? |
| Token cost | Sum from `_metrics.jsonl` |
| Human review minutes | Manual stopwatch |
| Cross-vendor portability | Run EDD spec through Codex; SDD spec needs translation |
| Spec authoring time | Manual stopwatch |
| Ambiguity catch rate | Inject 3 ambiguities per task; count catches |

### Phase 5 — Tabulate

```bash
# experiment/RESULTS.md
| Task | Time SDD | Time EDD | Iters SDD | Iters EDD | ... |
|------|----------|----------|-----------|-----------|-----|
| T-001 | 4h | 1.5h | 2 | 7 | ... |
| ...   | ... | ... | ... | ... | ... |
```

### Phase 6 — Compare against pre-registered hypotheses

For each hypothesis:
- Did the data support it?
- If not, was the failure mode predicted?
- Are there confounders (one task type dominated; cherry-picked)?

### Phase 7 — Publish RESULTS.md

Honest write-up:
- Where EDD won (and by how much)
- Where SDD won (and where it surprised you)
- Confounders and methodology weaknesses
- Recommended routing rules going forward

If EDD wins ≥5/8 metrics across ≥7/10 tasks → EDD is empirically supported.
If not → publish anyway; the boundary of EDD is now known.

## Timeline

| Day | Activity |
|-----|----------|
| 1 | Pre-register hypotheses; pick 10 tasks |
| 2-3 | Author 10 tasks twice |
| 4-5 | Execute 20 runs (parallelizable) |
| 6 | Ambiguity injection re-runs |
| 7 | Cross-vendor test (Codex) |
| 8 | Tabulate |
| 9 | Publish |

~9 days for a rigorous, publishable comparison.

## Why this matters

Without the experiment, "EDD is better" is opinion. With it, "EDD wins on
metrics X, Y, Z across N tasks under conditions C" is citable. The latter is
what the AI coding ecosystem needs and currently lacks.

## See also

- [edd-vs-sdd-honest-comparison.md](../references/concepts/edd-vs-sdd-honest-comparison.md) — theoretical comparison
- [eval-driven-development.md](../references/concepts/eval-driven-development.md) — the methodology itself
