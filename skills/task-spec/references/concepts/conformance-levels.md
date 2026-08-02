# Concept: Executor Conformance Levels (v3)

> **Status:** normative (v3)
> **Verified by:** `scripts/conformance-check.sh`
> **Reference executor:** `scripts/ref-executor.sh` (L2-conformant)

## Why conformance levels exist

The format's headline claim is *"any conformant executor can pick it up, do it,
prove it, and report it."* That claim is only credible if "conformant" is
**testable**. The cautionary tale is METR's Task Standard: a well-designed open
task standard that lost ecosystem mindshare to a tool with a better conformance
suite and adapters. A standard wins on its *conformance suite + adapters*, not its
prose. Conformance levels are how a consumer earns the word "conformant" by
observation, not assertion.

`safe-to-delegate.sh` certifies a **spec**. `conformance-check.sh` certifies an
**executor**. They are duals.

## The three levels (cumulative)

| Level | The executor must… | Observable test |
|-------|--------------------|-----------------|
| **L0** | Read the format and run the evals — given a signed spec, produce work that makes the Exit Check return 0. | Drive a solvable reference spec; `run-task-spec.sh` then exits 0. |
| **L1** | L0 **+ honor the lifecycle** — acquire the lock (`status → in-progress`) before working and release it (`status → done`) on success. | After success the spec's `status` is `done`. |
| **L2** | L1 **+ honor the retry budget** — on a spec it cannot satisfy within `budget_iterations`, stop and **park** (`status → parked`) with a reason rather than loop forever. | An unsolvable reference spec ends `parked`, and the executor does not time out. |

A plain bash loop can reach L0. L2 is the bar for an executor you would trust to
crank a backlog unattended.

## What "conformant" buys

- **L0** — safe for supervised, one-shot dispatch.
- **L1** — safe for a shared backlog: the lock prevents two executors double-picking
  a task, and the terminal status is trustworthy for orchestration.
- **L2** — safe for **unattended** operation: a runaway task self-terminates into
  `parked` instead of burning budget forever.

## Lifecycle ↔ A2A

The status transitions an executor drives map onto the A2A (Agent2Agent, Linux
Foundation) `TaskState` enum, so a conformant executor is interoperable with
A2A-aware dispatchers:

| Task-Spec status | A2A v1.0 `TaskState` | legacy lowercase alias |
|------------------|---------------------|------------------------|
| ready | `TASK_STATE_SUBMITTED` | submitted |
| in-progress | `TASK_STATE_WORKING` | working |
| blocked | `TASK_STATE_INPUT_REQUIRED` | input-required |
| done | `TASK_STATE_COMPLETED` | completed |
| parked | `TASK_STATE_FAILED` | failed |

The A2A v1.0 `TaskState` enum is SCREAMING_SNAKE_CASE with a `TASK_STATE_` prefix
and also defines `TASK_STATE_CANCELED`, `TASK_STATE_REJECTED`, and
`TASK_STATE_AUTH_REQUIRED` (no Task-Spec lifecycle source today; passed through if
supplied directly). The catch-all member is `TASK_STATE_UNSPECIFIED`.

Two helpers in `_lib.sh` are the single source of truth for this mapping:
`ts_a2a_state_v1()` echoes the canonical A2A v1.0 `TaskState` (right-pinned to the
spec), and `ts_a2a_state()` echoes the legacy lowercase alias kept for backward
compatibility (the surface the validator success line and conformance reports
emit).

## How to certify your executor

```bash
# Self-test the bundled reference executor (proves the harness):
bash scripts/conformance-check.sh --self-test

# Certify your own executor at a level (it must take the spec path as its last arg):
bash scripts/conformance-check.sh --level L2 --executor "my-runner --flags"
```

A green run prints `CONFORMANCE=L2` (machine-parseable). Publish the level your
executor reaches; that is the adapter's contract with the format.
