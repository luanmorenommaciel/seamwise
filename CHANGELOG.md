# Changelog

All notable changes to Seamwise are documented here.

## Unreleased

### Added

- Ship a PEP 561 `py.typed` marker so installed Seamwise exposes its types.
- Enforce branch coverage in the release gate with a minimum of 78 percent.

### Changed

- Split `seamwise.engine` into a package of focused stage modules. The public
  `seamwise.engine` import surface is unchanged.

### Removed

- `docs/project.md` and `docs/seamwise.pdf`. Documentation will be rebuilt
  later; accepted decisions in `docs/decisions/` remain.

### Fixed

- `mypy` with no arguments resolved the installed package instead of the source
  tree and silently type-checked nothing. It now checks `src/seamwise`.
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
