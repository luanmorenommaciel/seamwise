# Runbook: Dark Factory queue rows as Task-Specs (the componentization dogfood)

> **Goal of this runbook:** show how the Dark Factory's per-type "done" criteria —
> today encoded as PROSE inside the driver's tick instruction — become a Task-Spec's
> runnable evals, so verification moves OUT of the scheduler and INTO the task. This
> is the C10 dogfood from the v3 change plan: the decoupling that lets the scheduler
> (loop-engine) and the executor (`/tsys:auto`) be swapped independently.

## The coupling problem

`tasks/dark-factory-driver.md` is the `/loop` tick prompt. Its steps 4–6 embed the
done-criteria for every onboarding in ~100 lines of prose the executor must honor:

- **Step 4 (trust-but-verify):** "the type's tests pass, the parser yields the exact
  detail count = trailer, registered in the parser registry, ruff clean."
- **Step 5 (deploy + Bronze check):** "verify Bronze = trailer count."
- **Step 6 (AUTOMATION doc):** "a type CANNOT be `shipped` without it."

Every rule the executor must satisfy lives in the SCHEDULER's prompt. That is the
exact coupling the task should remove: the scheduler should schedule, the task
should carry its own definition of done. When the done-criteria live in the
scheduler prose, you cannot swap the executor without re-reading and re-honoring
100 lines of tick instructions — and "the harness gets lost at the task" is the
predictable result.

## The decoupled shape

| Component | Today | With Task-Spec |
|-----------|-------|----------------|
| Unit of work | a queue row (type, spec, sample, status) | a Task-Spec whose `eval_N` ARE the done-criteria |
| Scheduler | driver prose doing scheduling AND verification AND deploy choreography | loop-engine doing ONLY scheduling: pick ready → dispatch → run the task's evals → mark shipped/stalled |
| Executor | `/tsys:auto` hardwired into the tick prompt | any conformant executor — the spec doesn't care |
| Gate | prose guardrails ("STALL if…") | `accept-task.sh` semantics + stall reasons in the metrics ledger |

## The done-criteria, as evals

A Dark Factory onboarding for type `{T}` becomes a Task-Spec whose Success Criteria
encode steps 4–6 directly. Sketch (the real spec fills in `{T}` and the sample):

```bash
# eval-1 (step 4): the type's unit tests pass
eval_1() {
  cd "$GIT_ROOT" && python -m pytest -q -k "{T}" >/dev/null
}

# eval-2 (step 4): parser yields detail count == trailer (reconciliation),
# and the parser is registered in the registry
eval_2() {
  cd "$GIT_ROOT" && python -c "
from src.core.parsers import get_parser
assert get_parser('{T}') is not None, 'parser {T} not registered'
" >/dev/null
}

# eval-3 (step 4): ruff clean on the new module set
eval_3() {
  cd "$GIT_ROOT" && ruff check "src/core/parsers/{T}_parser.py" >/dev/null
}

# eval-4 (step 6): the AUTOMATION doc exists (the hard ship gate)
eval_4() {
  ls "$GIT_ROOT/.claude/tsys/archive/{T}"/AUTOMATION_*.md >/dev/null 2>&1
}
```

The Bronze==trailer cloud assertion (step 5) is a `check_type: deterministic` eval
that queries the deployed pipeline — or, in a no-cloud run, a recorded artifact the
deploy step writes. The point is that **every STALL guardrail in the driver prose
maps to an eval that fails for the right reason**, exactly as `safe-to-delegate`
intends.

## The smallest first step (proven path)

You do NOT rewrite the whole Dark Factory at once. The minimal, reversible step:

1. For ONE queue row, author a Task-Spec (profile `standard`) whose evals encode that
   type's done-criteria as above. Gate it with `safe-to-delegate.sh --stamp`.
2. In the driver, replace step 4's prose checklist for that one type with a call to
   `run-task-spec.sh <spec>` — the executor now reads the task, not the tick prompt,
   for its definition of done.
3. After execution, run `accept-task.sh --stamp <spec>` instead of the prose
   trust-but-verify: it re-runs the evals from a clean checkout, checks the change
   set stayed within `touches_paths` (no stray writes — the in-place-worktree-bug
   guard the driver already worries about), and confirms the contract is intact.

If the tick gets SIMPLER and the stall behavior stays correct, the architecture is
validated and you migrate the next row. The driver shrinks toward pure scheduling;
the loop-engine becomes a conformant L2 consumer (see
`references/concepts/conformance-levels.md`).

## Why this is the right dogfood

The Dark Factory is already a component system (queue = goal state, driver =
scheduler, `/tsys:auto` = executor, gates). The only thing welding the components
together is WHERE the done-criteria live. Move them into the task and the seam
becomes a clean interface — which is the entire thesis of the open Task-Spec format:
*the task carries its own intent, behavior, verification, and guardrails, so any
conformant executor can pick it up, do it, prove it, and report it.*
