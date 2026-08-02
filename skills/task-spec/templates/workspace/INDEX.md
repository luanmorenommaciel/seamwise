# Converge Workspace

This directory is the project-local Converge control plane. Product code stays
in the repository's normal application directories; the artifacts here record
why work exists, what was authorized, how it ran, and what proved it complete.

## Lifecycle

`brain → docs → sketch → tasks → execution → loop → receipts`

| Path | Contract |
|---|---|
| `brain/` | Raw inputs and append-only discovery material |
| `docs/` | Reviewed product and technical decisions |
| `sketch/` | Decomposition, lanes, and consensus evidence |
| `tasks/` | Canonical Task-Specs and their lifecycle projection |
| `execution/` | Runtime contracts bound to signed Task-Spec hashes |
| `loop/` | Resumable execution state and human handoffs |
| `receipts/` | Write-once settlement evidence |

Task-Spec frontmatter is canonical. `tasks/_state.yaml` is a derived,
rebuildable projection. External trackers are optional projections, never the
authoring source.
