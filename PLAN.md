# Seamwise end-to-end implementation plan

Status: implemented `v0.1.0-alpha` candidate. Release/tag/publication remain
separate actions; final readiness is proven only by the sign-off command below.

The canonical target remains [`docs/seamwise.pdf`](docs/seamwise.pdf). This
plan orders implementation work; it does not amend the blueprint.

## Outcome

Ship one model-agnostic compiler and CLI that lowers Delivery Intent plus
evidence through seams, owning swimlanes, capability legs, a semantic task
graph, and validated Task-Specs. The same artifact engine must serve terminal,
Codex, Claude Code, and portable chat workflows without duplicating canonical
logic.

## Build sequence

| Stage | Deliverable | Exit gate |
| --- | --- | --- |
| 0. Pin and extract | Converge v0.1.0 Task Pack copied without behavioral change | Source manifest, byte hashes, and donor conformance commands agree |
| 1. Contract first | Versioned schemas, result envelope, tokens, exits, fixtures, and accepted decisions | Positive and negative contract tests pass |
| 2. Compile | Four transformations, workspace authority, source verification, lineage, causal dependencies, contention, reports, and bounded agent context | Positive, adversarial, stale-hash, tamper, cycle, collision, causal-gap, forbidden-scope, and unprovable-node tests pass |
| 3. Package | `seamwise` and `task-spec` CLIs, wheel, plugin manifests, shared skills, and idempotent installers | Clean build and clean-environment install pass |
| 4. Prove | Rate-limiting intent becomes a reviewed, lineage-complete, validated, unsealed Task-Spec DAG | Every leaf backlinks to intent and the PDF steel thread passes end to end |
| 5. Sign off | Release check, isolated Codex/Claude installs, chat packet, docs command replay, and independent adversarial QA | One release command passes with zero hidden gaps; credentialed host checks are labeled separately |

## Explicitly deferred

- governed lesson promotion and Converge settlement/learning loops;
- domain-specific brownfield or hybrid discovery adapters beyond the general
  evidence-backed recipe contract;
- receipt-owned, transactional in-place revision and projection archival; v0.1
  requires revised recipes to start in a clean checkout or worktree;
- authenticated remote MCP, hosted service, marketplace publication, and
  credentialed host behavior outside the explicit live doctor probes.

## Experience contract

1. `seamwise init` creates one durable workspace and prints the exact next step.
2. `seamwise status` and `seamwise next` make resuming self-explanatory.
3. Each stage prints one stable token and, with `--json`, one versioned envelope.
4. A blocked gate names the missing evidence or decision and never manufactures
   progress.
5. `seamwise prepare` invokes only missing transformations and never preflights
   or seals implicitly.
6. `seamwise install` previews exact host changes, writes receipt-owned files,
   verifies hashes, and rolls back on failure.
7. Codex, Claude Code, and chat adapters call the same CLI and consume the same
   artifacts.
8. Explicit `tasks seal` is the only Seamwise command that may write dispatch
   authority.

## Sign-off command

The repository will expose one deterministic release command that runs format,
lint, type, schema, unit, conformance, installer, packaging, documentation, and
end-to-end checks from a clean fixture. A successful command is necessary for
sign-off; unsupported credentialed marketplace or hosted-chat claims remain
reported gaps rather than inferred success.
