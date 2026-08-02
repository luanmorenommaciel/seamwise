# Changelog

All notable changes to **Converge** are documented here — the CLI (`bin/cvg`), the
twelve skills, and the task-spec engine, which ship as ONE unit at ONE version.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

The version lives in the root `VERSION` file and nowhere else authoritative.
Every declaration in the package must equal it, and
`tests/test-version-unity.sh` fails the build if one drifts; bump `VERSION`, then
run that gate with `--sync`. Release versions unify; **schema/format versions
deliberately do not** (`format_version: 3`, `VALIDATOR_VERSION`,
`agent_contract.version`, `hmac-sha256-v2`) — those describe data contracts whose
whole purpose is to change independently of a release.

## A note on the numbering below

Entries from **3.6.0 and earlier describe the `task-spec` skill alone**, when it
versioned itself independently — this file began life as
`skills/task-spec/CHANGELOG.md`. That history is kept verbatim because it is the
real lineage of the engine now at the centre of Pass 5; only the numbering
convention changed. From **0.1.0 onward, one entry covers the whole package.**

---

## [Unreleased]

(nothing yet — everything below ships in 0.1.0)

---

## [0.1.0] — 2026-07-30

The first release where the number means the same thing everywhere.

### Added
- **One version for the whole package.** Root `VERSION` is the single source of
  truth; all skills declare `metadata.version`, and `bin/cvg`, the
  task-spec engine, the Pass 0 / Pass 1 gates and both JSON manifests agree with
  it. `tests/test-version-unity.sh` gates it and is proven to fail on drift.
- **Pass 2 finally has a suite** (`skills/tech-req-to-adrs/tests/run-tests.sh`,
  38 rows). It was the only pass in the chain with none, so `CHECK_ADR` had never
  been shown capable of refusing a bad ADR set. The suite carries counter-tests:
  advisories must stay advisory, and modal design language legitimate in
  *Consequences* must not be flagged the way it is in *Decision*.
- **Every suite in the package now runs in CI** — nine existed that the workflow
  never invoked, including Pass 4, THE BARRIER. `tests/test-ci-covers-every-suite.sh`
  keeps that list honest by failing with the exact path when a suite is unwired.
- **One changelog to rule them all** — this file, promoted from
  `skills/task-spec/CHANGELOG.md`.
- Regression rows for each of the fixes below, every one proven to fail against
  the pre-fix code: the shadow board, the anchor agreement between the two index
  writers, and — the load-bearing one — a **differential** in
  `tests/test-loop-kernel.sh` showing a run whose tracker bridge fails lands on
  exactly the state and exit code of one whose bridge succeeds. Stated as a
  comparison rather than a hardcoded state, because a constant would pass just
  as happily if the board were the thing dictating it.
- **`--post-hoc` mode on `write-execution-receipt.py`** — evidence for a spec
  that finished after binding (moved into a status bucket, frontmatter stamped
  by the POST-gate). Refuses unless the sign-off HMAC still verifies, records
  both the current and bind-time spec hashes, and names its own provenance in
  `generated_by`. Written for the ninth landing's missing receipt (below); along
  the way the writer turned out to be a fourth site of the "done/ is invisible"
  class.
- **The first `## Holdout` blocks** — two XS specs (`obs-rowcounts`,
  `obs-fence`) authored to give tier 2 its first real work; the judge-only
  section is excluded from the 7B worker brief. See **Proven**.
- **The 0.1.0 documentation set** — two canonical PDFs
  (`docs/converge-v0.1.pdf`, `docs/task-spec-v0.1.pdf`) and four interactive
  HTML walkthroughs under `presentation/`, replacing the pre-unification
  v6 / v3.6.0 documents.
- **Claude Code plugin marketplace install** — `.claude-plugin/plugin.json` +
  `marketplace.json` make the repository itself an installable plugin:
  `/plugin marketplace add luanmorenommaciel/converge` then
  `/plugin install converge@cvg` ships all the skills AND puts `bin/cvg` on
  the session PATH — over git, no package manager, nothing to authenticate.
  Both manifests are enumerated by the version-unity gate.
- **The one-line install** — `install.sh` now bootstraps itself when run
  standalone (`curl -fsSL …/install.sh | bash`): it shallow-clones the released
  source to a temp dir and hands off to the installer inside the clone.
  Copy-only by design (no durable checkout to symlink against), no TTY
  assumed, `CVG_REF` pins an exact tag, `CVG_REPO_URL` installs from a fork.
- **The npm door** — a root `package.json` ships the whole unit as an npm
  package installable straight from git, no registry account required:
  `npm i -g github:luanmorenommaciel/converge` puts `cvg` AND `cvg-install`
  (the skills installer) on PATH; `npm i -D` + `npx cvg` works project-local.
  The package embeds `bin/`, the whole `skills/` catalog, and the plugin manifests,
  so the CLI resolves its own home inside the installed package. Both
  installer entrypoints resolve npm's bin symlinks before locating
  themselves; a CI step asserts the packed tarball carries every anchor.
- **`conductor-steps` — the twelfth skill: the descent's sequence layer.**
  Derives which pass is CURRENT and which comes NEXT from workspace evidence
  (each pass leaves artifacts in a known `cvg/` folder — no stored state, no
  session memory), enforces order fail-closed with pre/post hooks, and owns
  the canonical pass prompts. Surfaced in the CLI as **`cvg next`**: the
  evidence board, the next pass, its steering prompt, and its closing gate in
  one instant, read-only call. Evidence presence is never a verdict — the
  gates stay authoritative. Born from the first uc-01 conducted run, to cut
  per-session cognitive load and keep the chat-driven descent in order.
  Proven by a 19-check hermetic suite wired into CI.
- **Canonical pass prompts** — `cvg init` now seeds `cvg/brain/_prompts/`
  with one steering blueprint per pass (pass-0-capture … pass-8-loop plus a
  README with the folder-discipline map). The prompts canonize how each pass
  is driven from a harness chat: mission, inputs, hard boundaries (never open
  held-back material, never edit a sealed eval), procedure, artifact
  destinations, and the exit gate with its token. Born from the first uc-01
  proving-ground run, where the steering lived only in the conductor's head.
- **Grok Build is a first-class harness** — the installer now writes a third
  skills directory, `.grok/skills/` (Grok's native project-level discovery
  path), alongside `.agents/skills/` (Codex + Kimi) and `.claude/skills/`.
  Grok also reads Claude Code marketplaces and the `AGENTS.md` family
  natively, so the marketplace door and the shared skills serve it too.
- **The readme, rewritten as a front door** — 60-second quickstart, one
  flow diagram, the nine passes as a table, three install paths ranked by
  friction, and a Status section where every claim links to the suite that
  proves it. 720 lines became ~270.

### Changed
- Per-skill licence claims removed; the root `LICENSE` (MIT) governs the unit.
  `task-specs-to-issues` had claimed Apache-2.0 inside an MIT repository.
- `compatibility` is nested under `metadata` in every skill (it was top-level in
  one).

### Removed
- **`agents-kbs-tech-stack`** — the legacy harness donor, deleted rather than
  shipped. Pass 7B absorbed its cross-tool emitter pattern long ago, and a
  reference audit found nothing left invoking it — not `bin/cvg`, not any
  skill's scripts, only the catalog naming it. The catalog then stood at
  eleven (9 spine + 2 utility; `conductor-steps` later made it twelve); its CI
  suite retires with it; the package stays recoverable from git history.
- **The `uc-analytics` proving ground** (`tests/uc-analytics/`) — the
  greenfield use case the descent 0→8 was first closed on. Its evidence is
  summarized under **Proven** below and preserved in git history; the shipped
  package carries no project-specific content. A CI step now asserts nothing
  shipped still depends on it.
- **`tests/e2e-test-engine`** — the domain-flavored golden fixture (a toy
  data stack with a designed-RED eval). Same reason: the released package is
  domain-agnostic. End-to-end coverage lives in
  `tests/test-clean-room-install-e2e.sh`, which builds a throwaway repository
  and proves the full install → init → bind → loop → accept → receipt chain
  with a stub engine — no domain fixture required.
- **`PLAN.md`** — the internal working document. The backlog now lives on the
  project's issue tracker; the shipped repository records the present
  (readme, this changelog, the surface ledgers), not the working state.

### Fixed
- **Nine symptoms of one root cause**: gates deriving their own answer to "where
  is the workspace / what changed / where do lifecycle directories live". The
  first task to ever FINISH broke four of them at once, because nothing had
  previously moved a spec into `tasks/done/`. `ts_workspace_root` centralises the
  derivation; the remaining call sites are tracked as **D1**.
- **Pass 8's outward legs had never executed.** Every run before this release
  settled locally, so the Linear board-write (`ID!` where `team(id:)` takes
  `String!`) and the PR leg (a commit sha handed to `gh pr create --base`, which
  requires a branch) were shipped and unproven. Both fixed and exercised live.
- `plugin.json` / `marketplace.json` were left at `3.6.0` by the first pass of the
  version unification — caught by `lint-skill-docs.sh`, and the unity gate now
  enumerates JSON manifests too.
- **A finished spec was starting a second board.** `validate-task-spec.sh` wrote
  `_state.yaml` as a plain sibling of the spec, but `transition-status.sh` moves a
  finished spec down into a status bucket (`done/`, `parked/`, `queue/`). So
  validating anything already moved built a SHADOW index *inside the bucket* —
  holding that one task — while the real index beside it went stale and unread.
  Found as an untracked `cvg/tasks/done/_state.yaml` on the proving ground
  carrying 1 of 9 tasks. `rebuild-state.sh` has always scanned buckets
  recursively into ONE index at the backlog root; this is the writer catching up
  to the reader. A **fifth** symptom of the nine-symptom root cause above —
  nothing had ever moved a spec into `tasks/done/` before the first task
  finished.
- **…and the two index writers disagreed on what paths are relative to.** The
  validator anchored at the parent of `tasks/`, which is right only for the bare
  layout; under `cvg/tasks` it names `cvg/` and emits `tasks/done/T-x.md` where
  `rebuild-state.sh` emits `cvg/tasks/done/T-x.md`. Harmless only for as long as
  the two wrote to *different files* — the moment the shadow board was fixed they
  shared one, and a validate after a rebuild would have mixed two path styles in
  a single list. `STATE_DIR` and `ANCHOR` are now chosen in the same branch, so
  they cannot be sourced from two different roots.
- **Fail-soft is not the same as silent.** The Pass 8 tracker call discarded the
  bridge's output *and* its status, so a run printed "the board will follow this
  run" and nothing in its own log could confirm or deny it. That is how the
  broken Linear board-write survived weeks unnoticed: every log looked identical
  to a working one. The call is still fail-soft — the evals decide the verdict,
  never the board — but now **accounted**: output lands in
  `cvg/loop/<task>/tracker.log`, and a `TRACKER=OK|FAILED|SKIPPED` token prints
  beside `TASK_LOOP=`. An unverifiable claim in a log is worse than no claim.
- **The ninth landing had no receipt, because no landing wrote one.** The loop
  never settled `cap-freshness` — its only landing was BLOCKED, and completion
  was operator-driven — so no `result: pass` receipt ever existed. Closed
  honestly: the accept gate re-run dry against the settled tree, a `--post-hoc`
  receipt written, and the gap documented in the proving ground's receipts
  ledger rather than papered over (that ledger left the tree with the proving
  ground — see **Removed**).

### Proven
Backlog swept 9/9 on the `uc-analytics` proving ground (since removed from the
tree — see **Removed**; the runs live in git history and the merged PRs):
`TASK_LOOP=LOCAL_SETTLED` ×2 then `SETTLED` ×7 through merged PRs, the last
four green on the first iteration, board parity `CHECK_REGISTER=OK` at 9⇄9
with an empty ready frontier.

**Tier 2 has now graded real work, and both verdicts exist** (2026-07-29, on the
two `## Holdout` specs — cross-family in both directions, no anthropic model in
either seat):
- `obs-rowcounts` — codex built it green in one iteration; **kimi UPHELD** every
  holdout assertion → `TASK_LOOP=SETTLED`, PR #9, receipt on file.
- `obs-fence` — kimi built it green in one iteration; **codex REFUTED**: the
  fence swallows `OSError` and reports an unreadable surface as `FENCE=OK`,
  exactly the exit-code contract the holdout reserved for the judge. The kernel
  refused settlement → `TASK_LOOP=BLOCKED`, handoff written. *A green eval is
  necessary, not sufficient — demonstrated, not asserted.*

### Known gaps at 0.1.0
- The two shipped PDFs (`docs/*.pdf`) predate `conductor-steps` and still say
  "eleven skills"; they cannot be regenerated from this tree (their HTML
  sources were retired). Re-render at the next doc pass.
- `task-spec/SKILL.md` is 569 lines against skill-creator's own 500-line rule.
- Lessons exist for passes 0–3 only.
- The kernel's tier-2 judge timeout is fixed at the verifier's 300s default —
  a slow judge lands `BLOCKED` on work it never graded (`CVG_VERIFIER` wrapping
  `verify-work.py --timeout N` is the working escape hatch).
- `--resume` under worktree isolation cuts a FRESH worktree and restarts at
  attempt 1 — the checkpoint survives, the working tree does not.
- `generate-task-spec.sh` anchors `tasks/` at the git root, not the workspace —
  the seventh sighting of the D1 run-context class.
- `obs-fence` is deliberately left `BLOCKED` on the board: the refuted work and
  its handoff are the living demonstration of the refute path.

---

## [3.6.0] — 2026-07-24

### Changed
- **The L tier is no longer locked to one vendor.** `effort: L` previously
  hard-failed unless `execution_backend: glm`, which directly contradicted this
  format's own rule that `execution_backend` is an **OPEN STRING** — "the backend
  names itself; the values above are non-normative examples, not an allow-list."
  The gate's real intent is *an L leaf needs a **long-horizon builder***, not *an L
  leaf needs GLM*. It now checks membership in `TS_LONG_HORIZON_BACKENDS`
  (default `glm claude codex kimi`), overridable per fleet:
  ```sh
  export TASKSPEC_LONG_HORIZON_BACKENDS="claude codex kimi glm my-harness"
  ```
  Surfaced by a real user whose fleet is Claude Code / Codex / Kimi: an L-sized
  spec could not name the engine that was actually going to run it.
- `ts_backend_is_long_horizon()` added to `_lib.sh` as the single source of truth;
  validator, effort-gate doc and SKILL.md all updated to the neutral wording.
- `tests/test-effort-sizing.sh` gained claude/codex/kimi rows (14 rows, all green).

## [3.5.0] — 2026-07-23

### Added
- **`tracker_ref` — the vendor-neutral tracker backlink (receipt).** A new
  optional frontmatter field carrying `<tracker>:<issue-ref>` (e.g.
  `linear:ENG-42`, `github:#42`) or `(none)`. It is the *receipt* the
  `task-specs-to-issues` REGISTER pass (Pass ①) writes BACK into the spec after
  a successful upsert — **never authored by hand**. Design grounded in the SOTA
  spec↔tracker contract (agnostical/workplans #62, sdlc-bridge,
  spec-kit-github-issues): the **marker carried on the issue is the idempotency
  key**, so `tracker_ref` is a convenience backlink only and tooling MUST
  tolerate it being `(none)` (a CI run that cannot write back still resolves by
  marker). One mirror per tracker; the spec always wins on content.
- **Validator Check 2d** — `tracker_ref`, if present and not `(none)`, SHOULD be
  `<tracker>:<issue-ref>` (open-string tracker, mirroring `execution_backend`);
  a malformed value **warns, never blocks** — the field does not gate delegation.

### Deprecated
- **`linear_ref`** — the Linear-specific field is now a deprecated alias of
  `tracker_ref`. Still accepted (legacy fixtures carry `linear_ref: (none)`); a
  non-empty value warns and should migrate to `tracker_ref: linear:<ref>`. The
  template now emits `tracker_ref: (none)` in its place.

## [3.4.0] — 2026-07-21

### Changed — the fork collapses; task-spec becomes the universal sizing engine
- **Six-tier effort model (XS/S/M/L/XL/XXL), two KINDS.** LEAVES (XS/S/M/L) are
  directly-runnable atoms; NODES (XL/XXL) are decomposition directives that MUST
  declare a `children:` block (>=2 for XL, >=3 for XXL) and expand into leaf slices.
- **The SDD escape is removed.** The old gate routed `XL → SDD (AgentSpec/OpenSpec/
  SpecKit)` — a plan-driven fork. It now routes `XL/XXL → decompose into child
  Task-Specs`. There is one path: tasks all the way down (the "dark factory" model).
- **Write-surface budgets (research-grounded).** A leaf's `|touches_paths ∪
  creates_paths|` is gate-checked against its tier (XS≤1, S≤2, M≤3, L≤5); a breach
  WARNS "mis-sized — split or reclassify UP" (budgets expose coarse decomposition —
  Young/Anthropic/Vaughan/Vest, 2026). L still requires `execution_backend: glm`.
- **New frontmatter:** `children:` (a node's leaf slices); `parent:` recognized.

### Added
- `_lib.sh`: `TS_SIZES`, `ts_size_is_valid`, `ts_size_is_leaf`, `ts_size_writes_max`,
  `ts_size_min_children`.
- `tests/test-effort-sizing.sh` — 11 discriminating rows across all six tiers +
  decompose-or-fail + mis-size warning + unknown-size refusal.
- `references/examples/T-20260721-ex-{xs,s,m,l,xl,xxl}-*.md` — one worked, validating
  example per tier (the XXL backbone → XL swimlanes → M/S/L legs recursion).
- `references/concepts/effort-gate.md` rewritten for the six-tier, single-path model.

### Fixed
- `validate-task-spec.sh`: a node with no write surface (`touches_paths: []`, no
  creates) no longer aborts the validator under `set -e`.

## [3.3.0] — 2026-07-17

The **decomposition shape** release (MINOR — additive guidance; `format_version: 3`
unchanged, every existing spec validates identically). Field-tested patterns from
external best-of-breed skills, absorbed into the authoring workflow.

### Added

- **Vertical-slice rule ("cut tracer bullets, not layers").** Feature atoms prefer a
  narrow but complete path through every layer over a horizontal slice of one layer —
  the eval defines *done*, the vertical cut defines *worth doing alone*.
- **Context-window sizing ceiling.** An atom must fit — spec, cited ADRs, touched
  files, working diff — in one fresh executor session; if not, split and wire
  `depends_on`.
- **Breakdown quiz before stub generation.** Present the proposed atoms (title,
  edges, end-to-end deliverable) and confirm granularity/edges/merges with the user
  BEFORE `batch-generate.sh` — regenerating stubs is cheap, re-cutting a half-built
  backlog is not.
- **Expand–contract sequencing for wide refactors.** Mechanical whole-codebase
  changes (rename, retype) are cut as expand → migrate-in-batches → contract atoms
  instead of being forced into a tracer bullet.

---

## [3.2.0] — 2026-07-06

The **size-aware routing** release (MINOR — additive; `format_version: 3` unchanged, every
existing spec validates identically). Turns the effort field into an engine-aware dispatch
signal and completes the "atomic, engine-agnostic task creator" thesis.

### Added

- **Size → engine recommendation.** The effort gate now maps t-shirt size to a recommended
  builder: `XS/S/M → Kimi` (sprinter, atomic cranks), `L → GLM` (marathoner, long-horizon),
  `XL → SDD` (route out). The recommendation is **advisory** — a dispatcher heuristic keyed
  off `effort`, expressed in `runbooks/dispatching-a-task-spec.md`. It never overrides an
  author's explicit `execution_backend` and keeps the agent-contract C9 black-box guarantee
  intact (see `references/concepts/agent-contract.md`).
- **New `Size → engine recommendation` table** in the dispatch runbook.

### Changed

- **Effort gate is now size-tiered and engine-aware** (`scripts/validate-task-spec.sh`,
  `references/concepts/effort-gate.md`):
  - `XS/S/M` — accepted (unchanged behavior; XS was previously an undocumented enum value,
    now defined: ≤ 2 hours, trivial one-liner).
  - `L` — **newly accepted, but ONLY with `execution_backend: glm`**, and only if it carries
    ONE coherent machine-checkable done-condition. An L spec on any other backend is a hard
    error → decompose into S/M atoms (which recommend GLM) or route to SDD. The relaxation is
    narrow and loud (a validator WARNING is emitted on every accepted L spec).
  - `XL` — rejected → route to **SDD**. The escalation target is broadened from AgentSpec-only
    to a menu: **AgentSpec / OpenSpec / SpecKit**. XL is the top t-shirt tier ("XXL" and larger
    live here in prose).
- **`execution_backend` examples** trimmed to the current fleet: `any, claude, codex, kimi,
  glm, gemini` (dropped `cursor, agentspec, anthive, taskship` from the non-normative example
  list — the field remains an OPEN STRING, so those still validate).
- **Dispatch runbook** engine table refreshed: added `glm`, removed `taskship`/`anthive` rows,
  and reframed each engine by fleet role (Claude orchestrates · Codex reviews · Kimi/GLM build).

### Rationale

L is the one tier where relaxing atomicity is defensible: a 3–7 day task can occasionally
have a single coherent done-condition that a 1M-context, long-horizon engine (GLM) sustains
across hundreds of tool-call rounds — a capability the sprinter class does not have. Gating L
to `glm` makes the relaxation earn its keep rather than opening the gate for every backend.
Everything at XL and beyond stays out of Task-Spec by design: the spec phase itself is the
work, which is what SDD is for.

## [3.1.1] — 2026-07-01

The **Anthropic-conformance patch** (PATCH — no format change; `format_version: 3`
unchanged, a v3.1.0 spec validates identically). Brings the skill's own frontmatter into
compliance with Anthropic's official Skill validator (`skill-creator/scripts/quick_validate.py`)
without touching a single crown-jewel mechanic.

### Changed

- **`version` moved from the frontmatter top level into `metadata.version`.** Anthropic's
  skill spec forbids a top-level `version` key (allowed: name, description, license,
  allowed-tools, metadata, compatibility). The canonical value is unchanged (`3.1.0`); only
  its location in `SKILL.md` moved. `plugin.json`, `marketplace.json`, and
  `_lib.sh:TASKSPEC_VERSION` are untouched.
- **`scripts/lint-skill-docs.sh` (Check 2) now reads `metadata.version`** first, with a
  legacy top-level `version:` fallback, so the dogfood doc-consistency lint stays green.
- **Description arrow `↔` ASCII-ized to `behavior-to-eval`** — portability nicety; the
  validator permits the glyph (only `<`/`>` are banned), but ASCII travels everywhere.

### Not changed (the crown jewels — preserved exactly)

The 6 zones, the 9-phase closed loop (validate → safe-to-delegate → accept), the
behavior-to-eval traceability lint, the HMAC sign-off envelope + 3-tier policy,
`accept-task.sh` GATES A–E (incl. `--gold-sanity` Goodhart guard), the effort gate,
conformance levels L0/L1/L2, the open-string `execution_backend`, the 5-layer backlog
architecture, and every bundled script and concept doc are byte-for-byte unchanged.

---

## [3.1.0] — 2026-06-18

The **open-standard hardening release** (MINOR — `format_version: 3`, additive). Builds on
the v3.0.0 closed loop with a published machine schema, a generic backend-metadata field,
two opt-in acceptance gates that defend against 2026-era reward-hacking, the canonical A2A
v1.0 TaskState dispatcher, DAG cycle detection in the cross-task linter, and a decomposition
path from intent to N atomic specs. Backward-compatible: a v3.0.0 spec validates unchanged.

### Added

- **Post-execution `--gold-sanity` gate (accept-task.sh GATE E)** — the Goodhart-guard
  upgrade. BLOCKS a non-discriminating eval set (one that passes even on the UNPATCHED
  baseline) by reconstructing the baseline in an ephemeral git worktree at `--base` /
  frontmatter `baseline_ref:` / `reference_solution:`, running the current spec's evals there
  (must FAIL) and on the current state (must PASS). Degrades to a warn when git/baseline is
  unavailable. Off by default. See `scripts/accept-task.sh`.
- **`requires:` isolation block + acceptance GATE D** — an OPTIONAL frontmatter object
  (`base_image` / `deps` / `network`) declaring what the executor's sandbox must provide.
  `accept-task.sh` reports it (document-and-warn — the bash tool cannot enforce egress) and
  WARNS when a `full`-profile spec leaves `requires.network` unset. New `ts_has_requires` /
  `ts_requires_field` helpers in `_lib.sh`.
- **A2A v1.0 TaskState dispatcher (`ts_a2a_state_v1` in `_lib.sh`)** — emits the canonical
  `TASK_STATE_*`-prefixed members (`TASK_STATE_SUBMITTED|WORKING|INPUT_REQUIRED|COMPLETED|
  FAILED`, catch-all `TASK_STATE_UNSPECIFIED`). The v3.0.0 `ts_a2a_state` is retained as the
  stable lowercase legacy alias.
- **`depends_on` DAG cycle detection (lint-backlog.sh)** — the cross-task linter now detects
  `depends_on` cycles via `tsort` (with a pure-bash DFS fallback) and reports the involved
  nodes, alongside the existing dangling-edge (non-existent task) check.
- **Decomposition runbook + concept doc** — `runbooks/decomposing-intent.md` and
  `references/concepts/decomposition.md`: intent / PRD / set-of-calls → N linked atomic specs
  (flat parent index of stubs + per-task detail specs, `depends_on`/`parent` edges,
  holes-as-blockers via `status: blocked`).
- **Published JSON Schema (Draft 2020-12)** surfaced as the format's machine contract:
  `validate-task-spec.sh --emit-schema {frontmatter|agent-contract}` is the single source of
  truth; the frontmatter schema now declares `profile`, `parent`, `accepted*`, `requires`,
  `baseline_ref`, and `reference_solution`.

### Changed

- **`backend_metadata` replaces the vendor-named `codex_metadata` / `kimi_metadata`
  fields** — a single generic, optional executor-specific key/value map (the backend names
  itself). Reflected in `templates/task-spec.md.tpl`, `references/schemas/agent-contract.schema.json`,
  and `references/concepts/agent-contract.md`. Vendor neutrality at the field level.
- **`execution_backend` documented as an OPEN STRING in the schema** — the frontmatter
  schema lists `examples` (non-normative), not an `enum` allow-list; the dispatch table in
  `SKILL.md` now routes to the non-normative `runbooks/dispatch-recipes/` adapters instead of
  enumerating vendors as if normative.

### Migration

No action required — v3.0.0 specs validate unchanged. To adopt the new gates, add
`baseline_ref:` (or pass `--base`) and run `accept-task.sh --gold-sanity`, and/or add a
`requires:` block. Rename any `codex_metadata:` / `kimi_metadata:` to `backend_metadata:`.

---

## [3.0.0] — 2026-06-18

The **open-format / closed-loop release** (MAJOR — `format_version: 3`, additive).
Twelve coordinated changes turn Task-Spec into a vendor-neutral open format with a
verified consumer contract and a closed author→gate→dispatch→execute→**accept**
loop. Every change is backward-compatible: a v2.2 spec with no new fields validates
as `profile: standard`.

### Added

- **Effort-scaled profiles** (`profile: lite | standard | full`) — scales required
  zones to a task's blast radius without weakening the eval moat. Absent → standard.
  See `references/concepts/profiles.md`.
- **Behavior zone** (Given/When/Then, stable `B-N` ids) — the BDD layer between
  intent and evals; required for standard/full, optional for lite.
- **Behavior↔eval traceability lint** — every behavior must be verified by ≥1 eval
  (`verifies: [B-N]`) and every eval must map to a declared behavior. Bidirectional
  coverage enforced as a validator error. The chain that makes the spec machine-checked.
- **`accept-task.sh` — the POST-execution acceptance gate** (the headline component).
  Re-runs evals from a clean checkout (must PASS), checks the change set is within
  `touches_paths`/`do-not-touch` (blast-radius / Goodhart guard), and re-verifies the
  sign-off HMAC (eval bodies unchanged). Stamps `accepted: true`. Closes the loop.
- **Conformance levels L0/L1/L2 + `conformance-check.sh`** — certifies an EXECUTOR
  (not just a spec) honors the contract: reads-format+runs-evals / lifecycle / budget+park.
  Makes "any conformant executor can pick it up" testable. `--self-test` included.
- **`ref-executor.sh`** — the canonical L2-conformant reference executor (~60 lines):
  the worked example of the consumer contract for adapter authors.
- **`parent:` frontmatter** — references a FEATURE-altitude PRD/SDD; the task DISTILLS
  it, never embeds it (preserves atomicity).
- **A2A lifecycle mapping** — Task-Spec status ↔ A2A (Linux Foundation) `TaskState`
  (`ts_a2a_state` in `_lib.sh`); surfaced by the validator and conformance harness.
- **`ts_timeout` portable watchdog** in `_lib.sh` — `timeout`→`gtimeout`→pure-bash
  fallback (macOS ships no `timeout`).
- Concept docs: `profiles.md`, `conformance-levels.md`.

### Changed

- **`execution_backend` is now an OPEN STRING**, not a closed enum — names any
  executor; bundled dispatch recipes (`runbooks/dispatch-recipes/`) are the
  non-normative adapter layer. Vendor neutrality at the field level.
- **Claims hygiene** — the closing motto no longer says "no humans in the loop";
  the honest claim is humans at intent + acceptance review. The HMAC envelope is
  documented as tamper-EVIDENT (drift guard), not tamper-PROOF (security boundary).
- `agent_contract` v2 schema validation now applies to `format_version: 3` (the
  contract schema is unchanged; v3 is additive at the spec level).
- Acceptance envelope floor: `accepted: true` requires `accepted_by` + `accepted_at`
  and presupposes `signed_off: true` (rejects hand-stamping, mirrors the sign-off floor).

### Migration

No action required for existing specs — they validate as `profile: standard` with
`format_version` unchanged. To adopt v3 features, add `profile:` and a `## Behavior`
section, or regenerate with `generate-task-spec.sh --profile <lite|standard|full>`.

---

## [2.2.1] — 2026-06-03

The **eval-runner stdin-hang fix** (PATCH). Pushes the v2.2 format from the 9.0
sign-off to **9.5** by closing the last reachable robustness gap: the eval runner
could block forever waiting on stdin. Same format, harder substrate.

### Fixed

- **`scripts/run-task-spec.sh` — eval runner no longer hangs on stdin.** The
  per-eval invocation (`bash -c "source …; eval_N"`) inherited the gate-runner's
  stdin. An eval body containing `read` — or any construct that consumes stdin —
  would **block indefinitely** waiting for input that never arrives, hanging the
  whole gate (and any CI dispatch reading its JSON). Both the per-eval runner and
  the Exit Check runner now redirect stdin from `/dev/null`, giving immediate EOF.
  This is load-bearing: the new `B:reads-stdin` fuzz case provably HANGS (killed
  at the 8s timeout, RC=137) with the per-eval guard removed and completes
  cleanly with it. The Exit Check guard is defense-in-depth (a malformed Exit
  Check body fails at script-build time, not on a stdin read), kept for symmetry
  with the per-eval path.

### Changed

- **Removed dead `overall_pass` accumulator** from `run-task-spec.sh`. It was set
  on per-eval failure but never read — the final verdict is the Exit Check's exit
  code, per the `signed_off` contract. shellcheck SC2034 surfaced it; deleting the
  vestigial state is cleaner than annotating it.

### Added

- **`tests/test-extractor-fuzz.sh` — adversarial fuzz of the extract-and-run
  path** (19 cases). (A) extraction correctness on heredoc-heavy bodies (arith
  `<<`, delimiter literally `bash`, fake fences/headers inside heredocs, nested
  and quoted heredocs); (B) robustness invariant (never hang, never leak a raw
  bash/awk/sed error) including the load-bearing `reads-stdin` case; (C)
  defense-in-depth coverage of the Exit Check runner. Honors `--version` via
  `ts_version_flag` (doc-lint Check 4).

---

## [2.2] — 2026-06-02

The **key-optional HMAC sign-off envelope** release (B2). The crypto deferred in
v2.1.1 is now HERE. `safe-to-delegate.sh --stamp` seals a real HMAC-SHA256 over a
canonical payload; `validate-task-spec.sh` Check 17 recomputes and compares.
Sign-off is no longer trivially forgeable by hand-edit — closing the gap the
`T-20260603-fake-envelope.md` fixture documented.

### Added

- **`scripts/_lib.sh` crypto floor.** `ts_sha256` and `ts_hmac_sha256` detect a
  provider in priority order (openssl → `shasum -a 256` → `sha256sum`). When only
  a plain sha256 tool is present, HMAC is built manually via the RFC-2104
  ipad/opad construction (block size 64) — byte-for-byte identical to
  `openssl dgst -sha256 -hmac KEY`. When NONE of the three providers exists the
  helpers return a sentinel and the gate degrades to structural-only (Tier 2);
  a missing crypto binary NEVER produces a broken install or a hard error.
  Adds `ts_resolve_signing_key`, `ts_keyid`, `ts_spec_body`, `ts_body_digest`,
  `ts_signoff_payload`, `ts_compute_signoff_sig`.
- **`scripts/safe-to-delegate.sh --stamp` now seals `signed_off_sig`.** After
  writing the three plaintext `signed_off*` lines, it computes HMAC-SHA256 over a
  canonical fixed-field payload (`id`, `body_digest` = sha256 of the spec body
  after the closing frontmatter `---`, `signed_off`, `signed_off_by`,
  `signed_off_at`) and writes `signed_off_sig: hmac-sha256-v1:<keyid>:<hex>`. The
  signed set EXCLUDES the `signed_off_sig` line itself and is independent of
  frontmatter line ordering, so the MAC verifies on the very next read.
- **`scripts/validate-task-spec.sh` Check 17 three-tier degrade.** The structural
  floor is unchanged. When a key + sig are present the MAC is recomputed and
  compared. **Tier 1** (key + sig + MAC verifies) = full crypto trust, exit 0;
  **Tier 2** (no key, or sig absent = legacy spec) = structural-only with a loud
  warning, exit 0 (never hard-fails for a missing key); **Tier 3** (MAC mismatch
  or malformed sig) = hard FAIL exit 1, "DO NOT DELEGATE: spec body or envelope
  modified after stamping".
- **`configs/setup-taskspec-signing-key.sh`** generates a 256-bit key, writes it
  chmod-600 to `.git/info/taskspec-signing-key` (when `.git` is a real directory)
  or prints `TASKSPEC_SIGNING_KEY` instructions (worktree `.git` is a FILE), and
  prints the keyid. Stored OUTSIDE version control.
- **Key resolution** (`ts_resolve_signing_key`): env `TASKSPEC_SIGNING_KEY` (file
  path → read it; else raw key material), then `.git/info/taskspec-signing-key`
  only when `git rev-parse --git-dir` resolves to a real directory, then no key
  → Tier 2.
- **Tests & fixtures.** `tests/test-hmac-envelope.sh` (keyed Tier-1/2/3 suite +
  portability-floor masking + `.git/info` fallback), wired as
  `tests/test-task-spec-skill.sh --suite hmac`. New fixtures
  `T-20260603-stamp-then-verify.md` and `T-20260603-tampered-body.md` (keyed,
  excluded from the default no-key oracle so the existing 15 fixtures still
  behave as before).
- **Schema.** `references/schemas/task-spec-frontmatter.schema.json` now declares
  the real `signed_off_sig` contract (pattern `hmac-sha256-v1:<keyid>:<hex>`,
  what it covers, key-optional). The previously-dead `signed_off_envelope` object
  stub is re-described as reserved for a future per-author detached-signature
  upgrade.

### Changed

- **`references/concepts/signed-off.md`** rewritten: crypto is HERE now (not
  "planned for v2.2"). Honest IS/IS-NOT — HMAC is symmetric, so it binds "a
  repo-key holder stamped this", NOT per-author non-repudiation (an asymmetric
  Ed25519/DSSE upgrade is the named future hardening). Threat model = an
  adversarial co-author who read the skill, not a remote supply-chain attacker.
  Documents the three tiers and the Tier-2 supervised-only policy.
- **`runbooks/dispatching-a-task-spec.md`** adds the mandatory sign-off-tier gate:
  Tier 2 is read/inspect/triage only — NOT dispatch-eligible for unsupervised
  crank — closing the downgrade-bypass (run the verifier without the key to reach
  the forgeable Tier-2 state). `safe-to-delegate.sh` surfaces the tier in VERDICT.

### Security

- HMAC is symmetric: a repo-key holder can forge a Tier-1 stamp. The envelope
  defends against an adversarial co-author who hand-edits an envelope or a silent
  post-stamp edit — NOT against an attacker who already holds the key. Per-author
  non-repudiation is explicitly out of scope and deferred to a future asymmetric
  upgrade.

### Fixed (round-5 adversarial review)

- **Shell-injection in the crypto-sealing path (HIGH).** `safe-to-delegate.sh`
  wrote `signed_off_by` via a `sed s|…|${STAMP_BY}|` substitution. A `--stamp-by`
  / `$USER` value containing `|` silently FAILED to seal while the gate still
  printed "Tier 1 crypto trust" (the `sed … && mv` chain suppressed `set -e`); an
  `&` silently mis-attributed the sign-off WITH a valid seal. Fixed by routing
  every envelope field (including `signed_off_sig`) through one injection-safe
  primitive, `ts_set_frontmatter_field` in `_lib.sh`, which carries the value via
  `awk -v` (never a sed delimiter). The five adversarial inputs (`build|42`,
  `a&b`, `team/build`, a full `s|.*|INJECTED` payload, an embedded space) are now
  regression-locked in `test-hmac-envelope.sh` Scenario 7.
- **Conformance suite silently no-op'd on bash 3.2 (HIGH).**
  `tests/conformance/run_conformance.sh` discovered fixtures with `mapfile`
  (bash-4-only). On macOS system bash 3.2 it printed "mapfile: command not found",
  left the fixture array empty, and reported success while testing NOTHING.
  Rewritten as a bash-3.2-safe `while read` loop so the vendor-facing conformance
  gate runs on the portability floor; `test-bash-portability.sh` section (d) now
  asserts the runner + adapters carry no bash-4-only constructs.

### Changed (round-5 adversarial review)

- **Tier-2 "supervised-only" is now an enforced control, not just prose.**
  `safe-to-delegate.sh` emits a machine-readable `TIER=N` line for a signed spec,
  and a new `--require-tier1` flag makes the gate exit non-zero on anything below
  Tier 1 — so a CI dispatcher branching on `$?` cannot crank a Tier-2 spec
  unsupervised. Documented in `runbooks/dispatching-a-task-spec.md`; covered by
  `test-hmac-envelope.sh` Scenario 8.
- **Cross-engine equivalence proof strengthened (B3).** The Python-vs-TypeScript
  oracle compared `eval_count` (a number) and four scalars. It now compares the
  FULL ORDERED `eval_ids` list and a canonicalized `validation_card` projection
  (`agent_contract` zones, `retry_policy`, success-criteria), so two consumers
  that find the same COUNT of evals but disagree on WHICH evals now diverge.
- **Worktree key-path docstrings corrected.** `_lib.sh` and
  `setup-taskspec-signing-key.sh` wrongly implied a worktree's `.git` being a file
  skips the `.git/info` key path. `git rev-parse --git-dir` resolves to the
  per-worktree gitdir, so the key IS found there — the comments now describe the
  real behavior (proven by the `.git/info` fallback test running in this worktree).

### Fixed (round-6 re-review — hardening the round-5 fixes)

- **`ts_set_frontmatter_field` now rejects multi-line values.** A value containing
  a newline or CR is refused with a clear error (return 2) and the file is left
  untouched — closing a residual injection path (a multi-line scalar would inject
  an extra frontmatter line). Regression: `test-hmac-envelope.sh` S9.
- **`ts_set_frontmatter_field` now hard-fails on un-writable frontmatter.** A spec
  with no closing `---` previously left the field silently unwritten while
  returning 0; the caller would then HMAC a spec missing the field. The awk now
  signals "not written" (`END { if (done==0) exit 3 }`) and the function returns
  1 with a clear error; `safe-to-delegate.sh` BLOCKs rather than sealing a
  half-stamped spec. Regression: `test-hmac-envelope.sh` S9.
- **Cross-engine oracle now normalizes whole-number floats** (`30.0` → `30`) so a
  YAML numeric-typing difference between the Python and TypeScript parsers cannot
  produce a false divergence in `test-portability-e2e.sh` Step 7.

### Fixed (round-7 convergence review)

- **`awk -v` escape-expansion injection closed (HIGH).** Round-6 rejected literal
  newline BYTES, but `ts_set_frontmatter_field` still passed the value via
  `awk -v`, which runs C-escape processing — so the two characters backslash+n
  (no newline byte, so the round-6 guard let it through) were expanded by awk
  into a real newline, injecting a forged extra frontmatter line via `--stamp-by`.
  The value is now carried through the process environment (`ENVIRON[]`), which
  does NO escape processing: every byte (`|`, `&`, `\`, backslash-n, tab) is
  written verbatim as one scalar. The primitive's docstring "verbatim incl. `\`"
  guarantee is now true. Regression: `test-hmac-envelope.sh` S9 case (c).
- **Conformance results.json write now fails loud on bash 3.2 (LOW).** A redirect
  failure on the `{ … } > results.json` brace group does not trip `set -e` on
  bash 3.2, so an unwritable target produced a green run with a stale artifact.
  The write goes via a temp file whose presence + a regular-file check on the
  destination are verified explicitly; any failure is a `FATAL` exit 1.

### Fixed (round-8 convergence — temp-file symlink hardening)

- **Symlink-following on the predictable `.$$` temp-write path closed (LOW).** The
  in-place editors write to a predictable sibling temp (`<file>.fmset.$$` /
  `.tmp.$$`) then `mv` it over the original. A shell redirect `> "$tmp"` follows
  a pre-existing symlink, so an actor with write access to the directory could
  plant one to clobber an arbitrary target. New `ts_prepare_tmp` helper (`_lib.sh`)
  `rm -f`s the temp path before every redirect at all five sites
  (`ts_set_frontmatter_field`, `validate-task-spec.sh`, `transition-status.sh`,
  `rebuild-state.sh`, `run_conformance.sh`), so the redirect always creates a
  fresh regular file. Scoped LOW — the temp is a repo-internal sibling, not in
  world-writable `/tmp` — but closed for defense-in-depth. Regression:
  `test-hmac-envelope.sh` S9 case (d).

---

## [2.1.1] — 2026-06-02

The "shippable for any agent" hardening release. Closes the 8 bugs surfaced by
the round-2 adversarial review of v2.1 and ships the cross-engine artifacts
(JSON schemas, reference consumers in Python and TypeScript, per-engine
dispatch recipes, RFC-2119 contract + conformance fixtures) that turn the
"vendor-portable" claim from rhetoric into a testable spec.

### Retraction — "HMAC envelope" was misleading

The v2.1.0 entry below described the `signed_off` envelope check as an "HMAC
envelope." That naming was wrong and is **retracted**. The check is a
**structural sign-off envelope**: it asserts that `signed_off: true` is
accompanied by `signed_off_by` and `signed_off_at` lines populated by
`safe-to-delegate.sh --stamp`. It catches the dominant failure mode
(accidental hand-stamping) but does **not** provide cryptographic protection
against adversarial hand-stamping — anyone with write access to the file can
populate the three lines manually and bypass the check. The `tests/fixtures/
T-20260603-fake-envelope.md` fixture documents this limitation by example.
Real HMAC crypto (with key management + rotation) is deferred to v2.2; until
then, every doc, error message, and code comment that previously said "HMAC"
now says "structural sign-off envelope."

### Added

- **WS-A — P0 silent-failure patches (Bugs 1, 2, 5).** `validate-task-spec.sh`
  now uses safe-default capture (`${var:-}`) for the three `signed_off*`
  reads, so a missing `signed_off_by:` line under `signed_off:true` produces
  a loud `hand-stamping detected` error at exit 1 instead of a 0-byte
  silent abort under `set -euo pipefail`. `safe-to-delegate.sh --stamp`
  no longer silently no-ops when envelope lines are absent — it now
  appends missing `signed_off_by:` and `signed_off_at:` lines via an
  `awk`-based frontmatter injection before the closing `---`.
  `tests/test-task-spec-skill.sh` Step 1 was broken since v2.1's
  generator-output rename (looked for `>>> Created`, generator now prints
  `Spec written:`); fixed to the new contract and locked by a new
  `tests/test-generator-output-contract.sh` regression guard.
- **WS-B — Generic inverted-eval lint (Bugs 3, 4).** `validate-task-spec.sh`
  Check 16 collapses the per-command regex stack (`grep -c`, `wc`, etc.)
  into a single coherent rule: any `$(...)` or backtick substitution
  followed by `|| (true|echo <int>)` within 4 lines of a numeric `-eq/-ne/
  -lt/-le/-gt/-ge` test against the captured variable, when the variable
  is not normalised via `${var:-0}` or `${var//[^0-9]/}`, fails validate.
  Catches backticks, `awk`, `python3`, `jq`, and any future substitution
  tool with one rule instead of whack-a-mole. New umbrella allowlist
  `# task-spec:allow-numeric-fallback` covers the legitimate exceptions.
- **WS-C — Honest renaming.** The "HMAC envelope" terminology was
  swept across `SKILL.md`, `README.md`, `references/concepts/signed-off.md`,
  `references/concepts/agent-contract.md`, `agents/task-architect.md`,
  `runbooks/dispatching-a-task-spec.md`, `runbooks/first-spec-walkthrough.md`,
  `tests/test-portability-e2e.sh`, `tests/test-task-spec-skill.sh`,
  `scripts/validate-task-spec.sh`, `scripts/generate-task-spec.sh`, and
  `tests/conformance/T-conformance-003-no-signed-off-mod.md` and replaced
  with "structural sign-off envelope." A new honest paragraph in
  `references/concepts/signed-off.md` describes the limitation and the
  v2.2 crypto options. A new `tests/fixtures/T-20260603-fake-envelope.md`
  fixture proves the bypass and is itself the documentation: yes, this is
  possible; here is how; we say so out loud. CHANGELOG keeps the historical
  v2.1.0 entry intact (no retroactive edits) and adds this retraction
  paragraph above it.
- **WS-D — Backlog-dir consistency + dogfood lint (Bugs 6, 7).**
  `transition-status.sh` now writes the metrics ledger to
  `$TASKSPEC_BACKLOG_DIR/_metrics.jsonl` instead of the hardcoded
  `tasks/_metrics.jsonl` — the skill now follows its own published rules
  about backlog-dir configurability. A new `ts_metrics_path()` helper in
  `_lib.sh` is the single source of truth so future ledger writers cannot
  re-introduce the drift. The dead `warn_count=$(echo ... | grep -c '^\s\+-'
  || true)` assignment in `safe-to-delegate.sh` (the gate using the very
  anti-pattern it bans) is deleted. `lint-skill-docs.sh` adds **Check 10**:
  run the Check 16 regex set against every `scripts/*.sh` (excluding
  `validate-task-spec.sh` itself, which contains the regexes as string
  literals) and assert zero matches. The skill now eats its own dog food.
- **WS-E — Machine-readable schemas + reference consumers (G1, G6).**
  `references/schemas/task-spec-frontmatter.schema.json` and
  `references/schemas/agent-contract.schema.json` (JSON Schema draft
  2020-12) mirror the validator's Check 2 / 2b / 2c and the validation-card
  YAML block. `references/schemas/README.md` ships copy-pasteable
  validation snippets for Python (`jsonschema`), Node (`ajv`), Go
  (`gojsonschema`), and Rust (`jsonschema`). `references/examples/
  consume-task-spec.py` (~100 LOC, stdlib-only) and `consume-task-spec.ts`
  (~120 LOC, `yaml`+`ajv`) prove that any agent — Python, Node, anything
  with a JSON Schema validator — can parse a Task-Spec, extract its
  agent contract, enumerate eval blocks, and return a structured object
  **without invoking bash**. New `validate-task-spec.sh --emit-schema
  {frontmatter|agent-contract}` flag is the single source of truth so
  engine vendors can pin a specific schema version. `tests/
  test-portability-e2e.sh` extends with a schema-fidelity step that runs
  the Python consumer against the golden fixture and asserts exit 0
  with correct field extraction.
- **WS-F — Per-engine dispatch recipes (G2).** New
  `runbooks/dispatch-recipes/` directory ships one recipe per
  `execution_backend` enum value: `claude-code.md` (`Task()` tool
  invocation, `agent_contract.read` zone consumption, terminal-output
  reporting), `codex.md` (Codex CLI + `codex_metadata` + exit-code
  conventions), `kimi.md` (Kimi-specific content extracted from the old
  Kimi-centric runbook), `gemini.md` (generic LLM CLI / completion API
  path), `taskship.md` (taskship-specific command), `anthive.md`
  (parallel-session dispatch + `output_artifacts` capture), and
  `custom.md` (the DIY escape hatch + v2.2 `dispatch_recipe:` field
  reference). Each recipe is bounded to ~80 LOC and structured
  identically (Prerequisites / Dispatch / Status reporting / Failure
  modes / See also). `runbooks/dispatching-a-task-spec.md` is rewritten
  as a **router** with a "Pick your engine" jump table at the top — the
  Kimi-centricity critique is closed.
- **WS-G — RFC-2119 contract + conformance suite (G4).**
  `references/concepts/agent-contract.md` "The contract" section is
  rewritten with explicit RFC-2119 verbs (MUST, MUST NOT, SHOULD,
  SHOULD NOT, MAY). 38 keywords now appear in the contract document
  (target was ≥10). A new "Conformance Test Suite" section enumerates
  the synthetic scenarios any engine claiming Task-Spec support must
  pass, and `tests/conformance/` ships **6 conformance fixtures**
  (`T-conformance-001-status-lock.md` through
  `T-conformance-006-do-not-touch.md`) designed to be vendored by
  engine authors into their own test suites. New `tests/conformance/
  README.md` documents the vendoring protocol. A new "What this
  contract does NOT cover" section in `agent-contract.md` lists the
  deliberate non-requirements (e.g., engines MAY use any internal LLM
  model; the contract is execution-side, not generation-side).

### Changed

- **Version bumped to 2.1.1** in `scripts/_lib.sh` (`TASKSPEC_VERSION`)
  and `SKILL.md` frontmatter (`version:`). `plugin.json` and
  `marketplace.json` version fields bumped to match.
- **`lint-skill-docs.sh` now runs 10 checks** (was 9). The new Check 10
  is the WS-D dogfood lint — same regex set as `validate-task-spec.sh`
  Check 16, applied to the skill's own `scripts/*.sh`.
- **`runbooks/dispatching-a-task-spec.md` rewritten as a router**, with
  per-engine details delegated to `runbooks/dispatch-recipes/*.md`.
- **`references/index.md` (and `runbooks/first-spec-walkthrough.md`
  Step 7) updated** to point at the new recipe files and schema docs.

### Fixed

- **Bug 1.** Missing `signed_off_by:` under `signed_off:true` no longer
  produces a 0-byte silent abort.
- **Bug 2.** `safe-to-delegate.sh --stamp` no longer silently no-ops on
  specs missing the envelope lines.
- **Bug 3.** Backtick form of the inverted-grep-c pattern is now caught
  by the generic Check 16 rule.
- **Bug 4.** `awk`, `python3`, `jq`, and any other substitution tool
  with a numeric-fallback footgun is now caught by the same rule.
- **Bug 5.** Default `tests/test-task-spec-skill.sh` invocation (no
  `--suite` flag) runs to completion past Step 1.
- **Bug 6.** `transition-status.sh` honors `TASKSPEC_BACKLOG_DIR` for
  the metrics ledger.
- **Bug 7.** Dead `warn_count` assignment using the banned inverted
  pattern removed from `safe-to-delegate.sh`.
- **Bug 8 (honesty).** "HMAC envelope" terminology is retracted and
  replaced with "structural sign-off envelope" everywhere except the
  v2.1.0 CHANGELOG entry (which is preserved as historical record).

### Deferred to v2.2

- **Real HMAC crypto on the sign-off envelope** (with key management +
  rotation). Requires a real secrets-management surface — `.git/info/
  task-spec-key`, gitignore policy, "what if key missing" UX. The
  v2.1.1 rename + the `T-20260603-fake-envelope.md` fixture proving
  the limitation are honest enough for this release; the crypto upgrade
  is the v2.2 unlock.
- **`dispatch_recipe:` custom-engine frontmatter field.** Requires a
  frontmatter schema bump. Holding until at least one real "custom"
  engine asks for it. `runbooks/dispatch-recipes/custom.md` documents
  the v2.2 path so vendors know what to expect.
- **Bash 3.2 vs 5.x + macOS / Linux / WSL matrix CI.** Requires
  GitHub Actions infra wiring. Local `test-portability-e2e.sh` is
  sufficient for v2.1.1; matrix CI is the next-level proof.
- **`scripts/conformance-check.sh <engine-binary>` driver.** Presupposes
  WS-G's conformance fixtures exist (this release ships them as files).
  Build the driver in v2.2 once vendors actually want it.
- **Property-based eval fuzzer.** The WS-B generic rule + 4 new
  inverted-eval fixtures cover the observed variants. Property fuzzer
  adds combinatorial coverage; deferred to v2.2 per the v2.1.0 CHANGELOG.
- **MCP self-provisioning preflight.** Failure mode is loud
  (`mcp: server not found`); manual install remains acceptable.

---

## [2.1.0] — 2026-06-02

The "no rough edges" hardening release. Closes the four defects exposed by the
ADF Decimal pilot crank and Codex adversarial review.

### Added
- **Single canonical version field.** `version: "2.1.0"` in `SKILL.md` frontmatter
  and `TASKSPEC_VERSION="2.1.0"` in `scripts/_lib.sh`. Every top-level script
  sources `_lib.sh` and supports `--version` printing `task-spec v2.1.0`.
- **CHANGELOG.md** (this file). Required to bump for every release per the format
  change protocol documented in `_lib.sh`.
- **`scripts/_lib.sh`** — shared bash helpers (path resolution, error printing,
  version handler). Single source of truth for version + skill root + configurable
  `TASKSPEC_BACKLOG_DIR`.
- **Inverted-grep-c lint** (WS4) — `validate-task-spec.sh` rejects 6 known
  inverted-eval-count variants (e.g. `count=$(grep -c X file || echo 0)` produces
  the literal string `"0\n0"` on zero matches, breaking integer comparison).
- **Eval-inversion fixture suite** (WS5) — `tests/fixtures/` ships 7 minimal
  fixture specs + `oracle.json` declaring expected verdicts, consumed by
  `tests/test-task-spec-skill.sh --suite fixtures`.
- **`safe-to-delegate.sh --stamp` is now THE named gate** (WS3) — the
  documented author flow points at the gate, not at the structural-only
  `validate-task-spec.sh`. New `references/concepts/signed-off.md` explains the
  autonomy contract; new `runbooks/dispatching-a-task-spec.md` closes the loop.
- **Portable distribution** (WS6) — `plugin.json` + `marketplace.json` ship at
  the skill root; `scripts/install.sh` rewrites for fresh-tempdir installability;
  `TASKSPEC_BACKLOG_DIR` env var overrides hardcoded `tasks/` for downstream users.
- **First-spec walkthrough + portability e2e smoke test** (WS8) — a new author
  at a new repo can follow `runbooks/first-spec-walkthrough.md` and produce a
  `signed_off: true` spec on first attempt; `tests/test-portability-e2e.sh`
  enforces it in CI.
- **Doc-consistency lint** (WS10) — `scripts/lint-skill-docs.sh` blocks future
  v1/v2 drift, version mismatches, and missing distribution files.

### Changed
- **All docs canonicalised to v2.1.** Every `Task-Spec v1` reference outside this
  CHANGELOG was swept to `Task-Spec v2.1`. Future-tense `v2 will add` roadmap
  lines were replaced with concrete CHANGELOG entries.
- **`generate-task-spec.sh` self-validates** (WS7) — on success, runs
  `validate-task-spec.sh` against its own output and prints a `Next: ...
  safe-to-delegate.sh --stamp ...` breadcrumb so authors are never lost between
  generation and gating.
- **`task-architect` agent template aligned** (WS9) — references v2.1,
  `execution_backend`, `signed_off`, and contains the "never hand-stamp" rule.

### Fixed
- **`validate-task-spec.sh:362` self-trip.** The script itself used
  `PLACEHOLDER_COUNT=$(grep -c '{{TODO' "$FILE" 2>/dev/null || echo 0)` — exactly
  the inverted-grep-c pattern the new lint catches. Rewritten using
  `${count:-0}` normalisation so the lint catches zero legitimate code in the
  skill itself.

### Deferred to v2.2
- MCP self-provisioning preflight (failure mode is loud; manual install
  acceptable for v2.1).
- Property-based eval fuzzer (curated fixture oracle suffices for v2.1).
- Per-file authorized-fields intent gate (belongs in the broker, not the spec
  skill).
- Backfill of v1/v0 CHANGELOG history (see git history).

---

## [2.0.0] — 2026-05-19

Initial v2 format release. See git history for the full change set; key additions
included the `signed_off` autonomy contract, `execution_backend` routing field,
`creates_paths` for greenfield tasks, `check_type: deterministic | llm_judge`
on per-eval validation, the 6-zone format (Intent / Contract / Rollback /
Observability / Guardrails / Operations), and `safe-to-delegate.sh --stamp` as
the autonomy-contract producer.

---

## [1.0.0] — 2026-05-19

Initial public release. The 4-zone EDD format with frontmatter + runnable bash
evals + validation card. See git history for the full change set.

[Unreleased]: https://github.com/luanmorenommaciel/converge/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/luanmorenommaciel/converge/releases/tag/v0.1.0
