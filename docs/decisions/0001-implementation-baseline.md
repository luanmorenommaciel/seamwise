# Decision 0001: Implementation baseline and source pin

- Status: accepted
- Date: 2026-08-02
- Accepted by: Luan Moreno M. Maciel through the explicit end-to-end build request
- Canonical target: `docs/seamwise.pdf`
- Canonical target SHA-256: `cad353a000ee1cffe5c41e56307c4d1ac164641853d21f78cbc90d8c8271e5ee`

## Context

The repository foundation required an explicit human transition before Phase 0.
The 2026-08-02 request authorizes that transition and requires complete CLI,
host-installation, proving-use-case, and end-to-end validation work.

The blueprint does not choose a runtime stack or pin the Task Pack donor. Those
choices must be recorded before implementation.

## Decision

1. Pin the Phase-0 donor to the private Converge repository at release `v0.1.0`,
   commit `b585ca792418924182e1c6a87f660a5f8afa07bd`.
2. Copy the Task Pack before refactoring it. Retain its MIT notice, record every
   copied path and SHA-256, and prove donor behavior with differential tests.
3. Implement Seamwise as a Python 3.11+ package using a thin CLI over
   behavior-bearing modules. Use Click for command contracts, Rich for the human
   surface, PyYAML for authored frontmatter/projections, and jsonschema for
   versioned machine contracts.
4. Keep provider and model credentials out of the core. Agents or injected
   adapters may collect evidence; the core records URI/path, freshness,
   confidence, and hashes, then deterministically validates and transforms
   artifacts.
5. Keep the authored recipe and cited evidence as canonical compilation inputs.
   Treat generated seam/lane/leg Markdown, graphs, draft Task-Specs, critical
   paths, reports, and chat packets as hash-bound rebuildable projections.
   Review receipts and explicit cryptographic seals remain separate authority
   records.
6. Implement the blueprint's full CLI and add the reversible UX commands
   `status`, `next`, `doctor`, `install`, and `uninstall`. These extensions may
   explain or distribute the workflow but may not bypass gates or authority.
7. `compile` means reviewed plan to semantic graph plus draft Task-Spec
   materialization. `prepare` runs only missing transformations and stops at the
   first closed gate. Neither command preflights nor seals.
8. Test the canonical PDF steel thread for rate limiting: schema -> effective
   policy resolution -> request 101 enforcement -> visible reason/decision
   telemetry. Metering remains a separate capability unless a later accepted
   decision changes the canonical path.

## Consequences

- The package has a small, explicit runtime dependency set instead of claiming
  zero dependencies.
- Semantic judgment remains in human/agent-authored inputs; the compiler is
  deterministic and fail-closed.
- Converge remains external authority for its upstream owner barrier and
  downstream Bind, Loop, settlement, and learning behavior.
- Hosted CI at the pinned donor commit is not evidence of success: its jobs were
  blocked before execution by account billing/spending state. Local donor gates
  are the Phase-0 executable evidence.
