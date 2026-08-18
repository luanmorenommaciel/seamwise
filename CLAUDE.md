@OPERATING.md
# Seamwise — Claude Code project guide

Seamwise is an architecture-aware decomposition compiler. It takes one approved
initiative and produces one reviewed `TaskPlan/v1` plus digest-bound lineage.
It does not materialize tasks and holds no dispatch authority.

Read [AGENTS.md](AGENTS.md) for the full agent contract. This file covers how to
work in the repository.

## The invariant

> Seamwise decomposes. Task-Spec contracts. Converge coordinates.

Never import, vendor, invoke, or reimplement Task-Spec. Never parse Task-Spec
Markdown or terminal prose as an integration contract. Seamwise emits two
boundary artifacts and stops; an external coordinator takes it from there.

## Commands

```bash
uv sync --extra dev --locked   # set up the environment
make check                     # the complete release gate — run before claiming done
make test                      # pytest only
make cov                       # pytest with branch coverage and missing lines
make lint                      # ruff format --check and ruff check
make typecheck                 # strict mypy
make build                     # wheel and sdist
```

`make check` is authoritative. It runs lint, strict mypy, tests with a coverage
floor, host-adapter and documentation validation, a wheel build, a clean-room
wheel lifecycle, host-plugin install/uninstall, doctor, and Git whitespace
checks.

The CLI pipeline, in order:

```bash
seamwise --workspace <path> init
seamwise --workspace <path> map --source <recipe.yaml>
seamwise --workspace <path> plan      # stops at DELIVERY_PLAN=NEEDS_REVIEW
seamwise --workspace <path> review --accept --reviewer <name> --reason <text>
seamwise --workspace <path> compile   # writes task-plan.json and lineage
seamwise --workspace <path> status
```

## Repository map

```
src/seamwise/         engine and CLI
  engine/             the decomposition stages (see below)
  cli.py              Click command surface, one JSON envelope per command
  contracts.py        schema validation
  io.py               atomic writes, locks, canonical JSON, digests
  safety.py           path traversal, case, glob, and symlink checks
  workspace.py        workspace state and status projection
  installer.py        Codex and Claude Code skill install/uninstall
  doctor.py           host and runtime checks
  render.py           Markdown artifact rendering
  reporting.py        HTML/JSON reports and agent-context packets
  taskspec_adapter.py TaskPlan and lineage projection (no Task-Spec import)
schemas/              8 versioned JSON Schemas
skills/               5 host skills shared by Codex and Claude Code
scripts/              release gate, validators, end-to-end proofs
tests/                pytest suites and the proving fixture
```

## Engine architecture

`seamwise.engine` is a package of stage modules with a strict one-way
dependency direction. Keep it acyclic when adding code.

```
support  →  recipe  →  seams  →  planning  →  graph  →  compilation
```

- `support.py` — leaf helpers: diagnostics, path canonicalization, events.
- `recipe.py` — recipe loading and fail-closed semantic validation.
- `seams.py` — recipe to seam map, and seam-map verification.
- `planning.py` — delivery plan build, human review acceptance, verification.
- `graph.py` — task-graph projection, topological sort, critical path, Mermaid.
- `compilation.py` — TaskPlan and lineage compilation, lineage inspection.

`engine/__init__.py` re-exports the nine public names. Import from
`seamwise.engine`, not from the stage modules, outside the package.

## Conventions

- Python 3.11+; ruff line length 100; rules `E,F,I,UP,B,SIM,RUF` with `E501` off.
- mypy runs `strict = true` over `src/seamwise`. The package ships `py.typed`.
- Branch coverage must stay at or above 78 percent.
- Every JSON-mode command returns exactly one `SeamwiseCLIResult/v1` object.
  Automation parses that envelope, never Rich terminal output.
- Exit codes: `0` success or intended boundary, `2` input required, `3` invalid
  command or contract, `4` integrity or topology conflict, `5` host runtime
  unavailable, `10` internal failure.

## Fail-closed rules

- `plan` always stops at `DELIVERY_PLAN=NEEDS_REVIEW`. Never bypass it.
- `compile` refuses without a current review receipt bound to the exact
  delivery-plan digest. Editing the plan makes the receipt stale.
- `compile` writes both artifacts in one lock-protected transaction, or neither.
- `status` independently rebuilds the graph, TaskPlan, and lineage projections;
  altered, partial, or stale artifacts return `STATUS=BLOCKED`.
- Add positive, adversarial, tamper, and failure-route tests before claiming a
  behavior-bearing change is done.

## Gotchas

- **Recipe evidence resolves through the repository root.** `_verify_local_recipe_sources`
  in `engine/recipe.py` tries `source.parent`, then the workspace root, then
  `assets_root()` — which is the repo root in a source checkout. The proving
  fixture cites `tests/fixtures/blueprint.md` and hashes it, so deleting or
  editing that file breaks most of the suite. Update the digest in
  `tests/fixtures/rate-limiting-recipe.yaml` and `scripts/clean_room_e2e.py`
  together if you ever change it.
- **The clean-room step needs Task-Spec exactly 3.8.0.** With any other version
  installed, `make check` stops at `clean_room_e2e.py` before running the
  Seamwise checks that follow it. CI pins the correct version.
- **`docs/` does not exist.** Documentation is being rebuilt. Historical
  decision records are recoverable from Git history.
