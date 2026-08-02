# EDD vs SDD — An Honest Comparison

> When Eval-Driven Development (Task-Spec) beats Spec-Driven Development (AgentSpec).
> When SDD beats EDD. When you should use both.

This is NOT a manifesto claiming EDD is universally better. It's a calibrated
analysis of when each methodology wins, written so you can honestly route work
to the right method.

---

## TL;DR

- **EDD wins** on small/medium tasks where success has a bash-checkable definition.
- **SDD wins** on large/multi-day tasks where human alignment matters more than machine velocity.
- **Use both.** Effort-gate small work to EDD (Task-Spec); large work to SDD (AgentSpec 5-phase).

---

## The two methodologies

### SDD — Spec-Driven Development

Best embodied by **AgentSpec** (v3.2.0, 58 agents, 24 KB domains, 5 phases).

```text
brainstorm → define → design → build → ship
```

Each phase produces a markdown doc. Humans review at phase boundaries. The agent
follows the spec. "Done" is determined by human review of the final result.

### EDD — Eval-Driven Development

Best embodied by **Task-Spec v3** (this skill).

```text
intent → Task-Spec → executor loops on evals → done | parked
```

A single markdown file with runnable bash evals. The executor loops on those
evals until they pass or the budget is exhausted. "Done" is determined by
all evals returning 0.

---

## Head-to-head on 8 dimensions

| Dimension | SDD | EDD | Winner |
|-----------|-----|-----|--------|
| **"Done" definition** | Human review | Bash evals return 0 | EDD (unambiguous) |
| **Iteration cadence** | Human-paced (hours-days) | Machine-paced (seconds-minutes) | EDD (faster) |
| **Cross-vendor portability** | Vendor-specific prompts | Bash + YAML universal | EDD (portable) |
| **Authoring time** | Faster (free-form prose) | Slower (writing evals is harder) | SDD (cheaper) |
| **Audit trail** | Narrative markdown | Machine ledger (`_metrics.jsonl`) | EDD (queryable) |
| **Subjective output (UX, copy)** | Works fine | Doesn't work — can't eval | SDD (handles fuzzy) |
| **Large multi-day work** | Designed for it (5 phases) | Refuses it (effort gate) | SDD (right tool) |
| **Catches ambiguity early** | Maybe (depends on reviewer) | Yes — eval fails fast | EDD (verifiable) |

**EDD wins 5/8. SDD wins 3/8.** Honest split.

---

## When EDD definitively wins

You should use EDD (Task-Spec) when:

| Condition | Why EDD wins |
|-----------|--------------|
| **The output has machine-checkable success criteria** | Bash evals define "done" unambiguously |
| **The task is S or M effort (PR-sized)** | EDD's loop overhead is amortized over small tasks |
| **You need cross-vendor portability** | Claude, Codex, Kimi, manual — all read the same evals |
| **You want autonomous overnight execution** | Loop until pass or budget; no human in the middle |
| **You want a forensic audit trail** | `_metrics.jsonl` answers "what happened?" mechanically |
| **You need machine-paced iteration** | Eval fail → retry in seconds, not days |
| **The work touches infra you can verify** | Docker up, ports open, files present — all bash-checkable |

---

## When SDD definitively wins

You should use SDD (AgentSpec 5-phase) when:

| Condition | Why SDD wins |
|-----------|--------------|
| **The task is L or XL effort (multi-day)** | EDD refuses these via effort gate; SDD is designed for them |
| **Success is genuinely subjective** | "Does this UI look right?" can't be a bash eval |
| **Human alignment is the bottleneck** | Politics, design reviews, multi-team buy-in — SDD's checkpoints help |
| **You're designing, not implementing** | Architecture decisions need narrative, not evals |
| **The work has cross-cutting concerns** | Multi-team coordination via 5 phases > single autonomous loop |
| **You need explicit human gates** | Compliance, security review, executive sign-off |
| **The output is documentation/strategy** | Specs about specs — meta work that's not bash-checkable |

---

## The trap: forcing EDD on subjective work

The single biggest mistake when adopting EDD is **trying to eval subjective
outputs**. Example failures:

| Task | EDD failure mode |
|------|------------------|
| "Make the landing page beautiful" | No bash eval can check beauty. Result: agent ships something that passes evals but looks awful. |
| "Write a compelling story" | Eval can check word count but not compelling-ness. Agent generates technically-passing prose that's flat. |
| "Improve developer experience" | Eval can check API surface but not UX feel. Agent ships breaking changes that score well. |

For these tasks, USE SDD. Task-Spec's effort gate doesn't catch this — it catches
size, not subjectivity. You must catch subjectivity at authoring time.

**Rule of thumb**: if you can't write 3+ bash evals that would catch real
failure modes, the task isn't EDD-ready. Use SDD.

---

## Hybrid pattern: SDD for design + EDD for implementation

The cleanest pattern in practice:

```text
1. SDD phase: brainstorm + define + design produce architecture decisions
                ↓
2. The design produces a backlog of Task-Specs (EDD)
                ↓
3. EDD phase: each Task-Spec runs autonomously with eval loops
                ↓
4. SDD phase: ship — human reviews integrated outcome
```

Architecture decisions are subjective and high-stakes — humans should review.
Implementation tasks are mechanical and verifiable — agents should loop until
they pass.

This is the **right way to use both AgentSpec and task-spec together**.

---

## Failure modes of each, side-by-side

### SDD's failure modes

| Mode | Symptom |
|------|---------|
| **Spec drift** | Phase 5 (ship) reveals the design didn't match reality; rework needed |
| **Phase paralysis** | Team gets stuck in brainstorm; nothing moves to build |
| **Reviewer bottleneck** | Phase boundaries require human review; sole reviewer becomes the constraint |
| **Verbose spec, vague success** | 5 docs produced, but "done" is still subjective at the end |
| **Vendor lock-in** | The 5-phase prompts are designed for Claude; Codex/Kimi need translation |

### EDD's failure modes

| Mode | Symptom |
|------|---------|
| **Eval gaming (Goodhart)** | Agent makes evals pass without solving the real problem |
| **Incomplete eval coverage** | Evals miss a failure mode; agent ships broken code that passes |
| **Flaky evals** | Eval randomly fails on second run; loop never terminates |
| **Subjective work forced through** | Task should have been SDD; ends up "passing" with bad output |
| **Authoring overhead** | Writing 4-6 evals per task is slower than prose; small tasks become slow to author |

Both have real failure modes. Neither is universally better. The right move is
**routing** — send subjective/large work to SDD, send objective/small work to EDD.

---

## Quantifying "wins" (the experiment protocol)

To move beyond "we believe EDD is better" to "we measured it," run the SDD vs
EDD experiment from `runbooks/empirical-experiment-protocol.md`:

1. Pick 10 real tasks
2. Author each twice (SDD spec + Task-Spec)
3. Execute each twice (SDD via AgentSpec, EDD via Task-Spec loop)
4. Measure 8 metrics
5. Pre-register hypotheses BEFORE running
6. EDD wins if it beats SDD on ≥5/8 metrics across ≥7/10 tasks

The experiment makes the claim falsifiable. Without it, this comparison is
opinion.

---

## The two-axis decision tree

```text
Is the output machine-checkable? (Can you write 3+ bash evals?)
│
├─ NO → Use SDD (AgentSpec)
│       Example: design review, UX copy, strategy doc
│
└─ YES → Is the work S or M effort? (One PR's worth)
         │
         ├─ NO (L/XL) → Use SDD (AgentSpec 5-phase)
         │              Example: new service, multi-week migration
         │
         └─ YES → Use EDD (Task-Spec)
                  Example: bug fix, parser update, docs polish, infra verify
```

That's the routing rule. Burn it into your project conventions.

---

## What about prompt-driven workflows?

A third methodology exists in the wild: **prompt-driven** (just paste a prompt
into Claude/Codex/Kimi and see what happens).

| Aspect | Prompt-driven | SDD | EDD |
|--------|--------------|-----|-----|
| Setup time | None | High | Medium |
| "Done" definition | Vibes | Human review | Bash evals |
| Audit trail | Conversation log | Multi-doc | Machine ledger |
| Reproducibility | Low | Medium | High |
| Best for | Exploration | Design + planning | Implementation + verification |

Prompt-driven is FINE for exploration ("what would this look like?"). It's NOT
fine for production work. Both SDD and EDD beat prompt-driven on production
metrics. Don't ship work that originated as a prompt without converting it to
SDD or EDD first.

---

## Honest claim

EDD is not a silver bullet. It's a sharp tool for a specific shape of work. The
revolutionary move isn't claiming EDD beats SDD universally — it's defining the
boundary and routing work cleanly between them.

Task-Spec v3 enforces the boundary structurally (effort gate, required evals).
AgentSpec handles everything beyond the boundary. Together they form the full
methodology stack.

---

## See also

- [task-spec-v1.md](task-spec-v1.md) — the format that embodies EDD
- [eval-driven-development.md](eval-driven-development.md) — EDD as methodology
- [effort-gate.md](effort-gate.md) — S/M/L/XL routing rules
- [../runbooks/empirical-experiment-protocol.md](../../runbooks/empirical-experiment-protocol.md) — the falsification protocol
