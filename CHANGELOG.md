# Changelog

All notable changes to Seamwise are documented here.

## Unreleased

### Added

- Derive the package version from the `VERSION` file so a release edits that
  file, the changelog, and the host plugin manifests the gate already checks.
- Include `Makefile`, `uv.lock`, and `assets/` in the source distribution so
  the published tarball can run the same locked release gate.
- Ship a PEP 561 `py.typed` marker so installed Seamwise exposes its types.
- Enforce branch coverage in the release gate with a minimum of 78 percent.
- Add `CLAUDE.md`, a Claude Code project guide covering the repository map,
  commands, engine stage order, conventions, and fail-closed rules.
- Add `make lint`, `make typecheck`, and `make cov` for the individual gate
  steps, and ship `AGENTS.md` and `CLAUDE.md` in the source distribution.

### Changed

- Split `seamwise.engine` into a package of focused stage modules. The public
  `seamwise.engine` import surface is unchanged.
- The release workflow publishes any `v*` tag that matches `VERSION`, not only
  `v0.2.0`.
- `make check` runs doctor and host-plugin install before the Task-Spec
  clean-room step, and clean-room exits `CLEAN_ROOM=BLOCKED` on a version
  mismatch.
- The CLI help and host skill descriptions no longer claim Seamwise emits
  Task-Spec leaves.

### Removed

- The unused `build` development extra. The gate uses `uv build`.
- The unused `assert_contract` helper.
- The leftover `.gitattributes` `*.png` rule after raster assets left Git.
- The whole `docs/` tree: `project.md`, `seamwise.pdf`, and the four accepted
  decision records. Documentation is being rebuilt in a later pass. The records
  remain recoverable from Git history.
- `brand/`, nine logo exploration files that no tracked file referenced and
  that shipped in no artifact.
- Four unreferenced files from `assets/`. Only `seamwise-hero.svg` is used,
  by the README header.

### Fixed

- Human-mode status and inspect tests now assert on JSON envelopes, so the
  release gate no longer depends on Rich color settings.
- `doctor` reports a failed check when `VERSION` is missing instead of raising.
- The release gate now runs `shellcheck` on `scripts/release-check.sh`.
- `mypy` with no arguments resolved the installed package instead of the source
  tree and silently type-checked nothing. It now checks `src/seamwise`.
- `.gitattributes` pinned whitespace handling for `skills/task-spec/**`, a path
  removed in 0.2. Replaced with a lockfile rule.
- The proving fixture cited `docs/seamwise.pdf` as its evidence source, so the
  test suite depended on a 3.7 MB document and 59 tests failed without it.
  Evidence is now `tests/fixtures/blueprint.md`, a small purpose-built file.

## 0.2.0 — 2026-08-16

### Changed

- Replaced the embedded Task Pack with a two-artifact engine boundary.
- Compilation now emits only reviewed `TaskPlan/v1` and
  `SeamwiseTaskPlanLineage/v1`; it never invokes Task-Spec or writes Markdown.
- Added `SeamwiseCLIResult/v1` and `SeamwiseCapabilities/v1` so external
  coordinators can negotiate version and contracts.
- Status independently rebuilds graph, TaskPlan, and lineage projections and
  reports zero materialized Task-Specs with `dispatch_authorized: false`.

### Removed

- Bundled Task-Spec runtime, skill tree, provenance manifest, and parity suite.
- The `task-spec` console script shipped by Seamwise.
- `seamwise tasks emit|validate|preflight|setup-signing-key|seal`.
- Direct Task-Spec skill installation through `--with-task-spec`.

### Security

- Compile writes TaskPlan and lineage in one atomic transaction, binds the
  review and canonical TaskPlan digests, and rejects partial or coordinated
  projection tampering.

## 0.1.0 — 2026-08-02

- Initial alpha implementation with the Phase-0 embedded Task Pack.
