# Conformance Test Suite — Agent Contract

This directory ships the **vendored conformance fixtures** for the
Task-Spec agent contract defined in
`../../references/concepts/agent-contract.md`.

Each fixture is a real `T-*.md` Task-Spec that exercises exactly one clause
of the contract. Engine authors run these fixtures through their engine to
demonstrate conformance.

## What this directory is for

The contract uses RFC-2119 keywords (MUST, MUST NOT, SHOULD, SHOULD NOT,
MAY) to define a wire protocol. The protocol is meaningful only if there
is a way to test that an engine honors it. These fixtures are that test.

If you are an engine author (you build a CLI, a runner, an orchestrator
that consumes Task-Spec), copy these files into your repo's test suite and
run them. A conformant engine produces a passing exit code on every
fixture it elects to support.

This directory also ships **one canonical reference driver**,
`run_conformance.sh`, plus a reference self-adapter under `adapters/`. The
driver is here so the skill can self-certify its own reference execution
path and so vendors have a worked example of the harness contract. You are
still expected to **write your own** harness against your engine (see "How
to vendor these fixtures" below) — the reference driver is an illustration
of the contract, not a dependency you ship.

## Files

| Fixture | Clause | Tests |
| ------- | ------ | ----- |
| `T-conformance-001-status-lock.md` | C1 | Atomic lock acquired before status change |
| `T-conformance-002-emit-enum.md` | C12 | Terminal state is one of the four allowed values |
| `T-conformance-003-no-signed-off-mod.md` | C6 | `signed_off*` envelope fields untouched during execution |
| `T-conformance-004-execution-backend.md` | C8 | `execution_backend` honored OR override is justified in the ledger |
| `T-conformance-005-budget-stop.md` | C13, C16 | Iteration stops at `budget_iterations` |
| `T-conformance-006-do-not-touch.md` | C5 | Engine refuses to write to Do-Not-Touch paths |

Alongside the fixtures, this directory ships the reference harness:

| File | Purpose |
| ---- | ------- |
| `run_conformance.sh` | Canonical reference driver (black-box, adapter-indirected) |
| `adapters/self.sh` | Reference self-adapter (the skill's own execution path) |
| `CONFORMANCE.yaml` | Optional waiver list (not committed by default) |
| `results.json` | Driver output: per-fixture verdict array (regenerated each run) |
| `_workdir/` | Per-fixture scratch area, reset before each fixture runs |

## The reference driver — `run_conformance.sh`

`run_conformance.sh` is the canonical reference harness. It is black-box: it
shells out to an **engine adapter** and never imports engine internals.

```bash
# Default: drive the fixtures through the reference self-adapter.
bash run_conformance.sh && echo CERTIFIED

# Point it at your own engine via env var (highest precedence)...
TASKSPEC_ENGINE_CMD="my-engine run" bash run_conformance.sh

# ...or via a flag.
bash run_conformance.sh --adapter ./adapters/my-engine.sh
```

### Adapter contract

The driver invokes the adapter once per fixture with three positional args:

| Arg | Meaning |
| --- | ------- |
| `$1` | absolute path to the `T-conformance-*.md` fixture |
| `$2` | absolute path to the `_workdir/` scratch area |
| `$3` | fixture stem (e.g. `T-conformance-001-status-lock`) |

The adapter drives the engine the way it would normally pick up a Task-Spec,
and leaves behind the `_workdir/` artifacts the fixture's own `## Exit Check`
asserts against. **The fixture is the oracle** — no golden outputs are kept.
`adapters/self.sh` is the reference adapter and shows the minimal, honest
state a conformant engine would produce for each clause.

### What the driver does, in order

1. **Self-test floor (runs first, before any engine work).** Every
   `T-conformance-*.md` fixture must itself pass `validate-task-spec.sh`
   (with `--skip-touches-paths --skip-id-filename`, since fixtures reference
   `_workdir/` paths and carry vendored ids). A malformed fixture would
   silently mislead a vendor, so the driver **hard-fails the whole run** at
   the floor — before any evals — if any fixture is invalid.
2. **Per-fixture loop.** Reset `_workdir/` per the fixture's Rollback Plan,
   invoke the adapter, then extract and run the fixture's own `## Exit Check`
   bash block (which calls the `## Success Criteria` evals).
3. **Selective conformance.** Read the optional `CONFORMANCE.yaml` waiver
   list (see below). Waived clauses report `WAIVE`, not `PASS`.
4. **Dual report.** Write `results.json` (a JSON array of per-fixture objects:
   `clause`, `fixture`, `verdict`, `evals_passed`, `evals_failed`,
   `waiver_reason`, `duration_sec`) and stream one `PASS`/`FAIL`/`WAIVE` line
   per fixture to stdout. The exit code equals the count of non-waived
   failures, so `run_conformance.sh && echo CERTIFIED` gates directly.

### `CONFORMANCE.yaml` waiver format

To waive clauses the engine does not support, drop a `CONFORMANCE.yaml` next
to the fixtures:

```yaml
waived: [C8]
reason: single-shot engine; no execution_backend selection occurs
```

- `waived:` is a simple bracketed list of clause ids (`C1`, `C8`,
  `C13`, ...). Whitespace and commas are tolerated.
- `reason:` (optional) is recorded as `waiver_reason` in `results.json`.
- Waiving a **load-bearing** clause (`C5`, `C6`, `C12`) is a hard error:
  the driver aborts non-zero, because an engine that waives those is not
  conformant (see "Selective conformance" below).

## How to vendor these fixtures

Engine authors are expected to **vendor** (copy) these fixtures into their
own repo rather than depending on this directory at runtime. Vendoring
gives you stability: the contract evolves, your test suite stays under
your own version control, and you choose when to re-vendor against a newer
contract release.

### Recommended layout

```text
your-engine-repo/
  tests/
    conformance/
      task-spec/                 # vendored from this directory
        T-conformance-001-status-lock.md
        T-conformance-002-emit-enum.md
        ...
        README.md                # this file
        VENDORED_FROM             # SHA + URL of source
      run_conformance.sh         # your harness that drives the fixtures
```

### Vendoring procedure

1. Clone the kurv-edp repo (or fetch the released archive) at the SHA you
   want to vendor.
2. Copy the entire `.claude/skills/task-spec/tests/conformance/` directory
   into your repo's `tests/conformance/task-spec/` (or a path of your
   choice).
3. Create a `VENDORED_FROM` file containing the source URL and the SHA you
   vendored from. Example:

   ```text
   https://github.com/<org>/kurv-edp/tree/<sha>/.claude/skills/task-spec/tests/conformance
   sha: <sha>
   vendored_at: 2026-06-02
   ```

4. Write a thin shell harness (`run_conformance.sh`) that:
   - For each `T-conformance-*.md`, drives your engine the way it would
     normally pick up a Task-Spec.
   - Captures the engine's emitted outcome and the contents of
     `tests/conformance/_workdir/`.
   - Compares against the success criteria embedded in each fixture.
5. Run the harness in CI on every commit. A regression in the harness is
   a regression in your contract conformance.

### Re-vendoring

When the contract changes (new clauses, retired clauses), the conformance
fixtures change too. Watch this directory's git history. To re-vendor:

1. Diff the new fixtures against your vendored copy.
2. For each delta, decide whether your engine still conforms.
3. If yes, copy the new files and update `VENDORED_FROM`.
4. If no, either fix your engine or document the waiver in your repo's
   `CONFORMANCE.md`.

## Selective conformance

The contract allows engines to waive specific clauses **if** the waiver is
documented in the engine's `CONFORMANCE.md`. For example, a single-shot
non-iterating engine may waive C13/C16 (budget-stop) because it does not
loop. A pure "executor" that never picks up new tasks may waive C1 and C3.

Document each waiver as:

```text
- Clause: C13/C16 (budget-stop)
- Waiver reason: this engine is single-shot; no iteration occurs
- Fixture skipped: T-conformance-005-budget-stop.md
```

Engines that waive C5 (Do-Not-Touch), C6 (envelope immutability), or C12
(emit enum) are NOT conformant; these clauses are load-bearing for safety
and ledger-readability.

## What this suite does NOT test

- **Generation quality.** A passing fixture proves the engine respects
  the protocol, not that it produces good code.
- **Performance.** No fixture asserts on wall-clock time beyond the
  per-eval `expected_duration_sec` (which is advisory).
- **Internal model selection, prompt strategy, retrieval, model routing.**
  See "What this contract does NOT cover" in
  `../../references/concepts/agent-contract.md`.

## Reporting conformance

When publishing your engine's conformance result, include:

- Source SHA of the vendored fixtures (from `VENDORED_FROM`).
- List of fixtures passed.
- List of fixtures waived (with reasons).
- List of fixtures failed (with diagnosis).

A conformance claim without these four lists is not meaningful.

## Related

- `../../references/concepts/agent-contract.md` — the contract itself
- `../../references/concepts/signed-off.md` — the autonomy gate
- `../fixtures/` — the skill's own internal regression fixtures (NOT for
  vendoring; those test the skill, not engine conformance)
