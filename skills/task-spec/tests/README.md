# task-spec skill — Self-Test Suite

## Running the tests

```bash
bash .claude/skills/task-spec/tests/test-task-spec-skill.sh
```

The suite is fully self-contained and runs in a temporary directory. It does **not**
read or write the real `tasks/` backlog.

## Test scripts (6)

| Script | Covers |
|--------|--------|
| `test-task-spec-skill.sh` | End-to-end author flow (generate → validate → transition → rebuild → archive); `--suite fixtures` and `--suite hmac` selectors |
| `test-hmac-envelope.sh` | Key-optional HMAC sign-off envelope: Tier-1/2/3 degrade, injection-safe field writes, `.git/info` key fallback |
| `test-extractor-fuzz.sh` | Adversarial fuzz of the extract-and-run path (heredoc-heavy bodies; never-hang / never-leak-raw-error invariants) |
| `test-bash-portability.sh` | bash-3.2 floor: core gate path + conformance runner carry no bash-4-only constructs |
| `test-portability-e2e.sh` | Cross-engine equivalence (Python vs TypeScript reference consumers) + schema fidelity |
| `test-v3-closed-loop-e2e.sh` | v3 closed loop: author → gate → dispatch → execute → `accept-task.sh` |

## Conformance suite

`tests/conformance/` ships the vendored executor-conformance suite — **6**
`T-conformance-*.md` fixtures (one per contract clause), the reference driver
`run_conformance.sh`, and the reference self-adapter `adapters/self.sh`. See
[conformance/README.md](conformance/README.md) for the vendoring protocol.

## Regression fixtures

`tests/fixtures/` holds **17** `T-*.md` regression fixtures (golden, hand-stamped,
inverted-eval variants, envelope-tampering cases) plus `oracle.json` declaring the
expected verdict per fixture. Consumed by `test-task-spec-skill.sh --suite fixtures`.

## What is covered

| Step | Script | Assertion |
|------|--------|-----------|
| 1 | `generate-task-spec.sh` | Creates a file with correct ID ↔ filename match |
| 2 | — | Fills the generated stub with a valid Task-Spec v2 |
| 3 | `validate-task-spec.sh` | Passes on a well-formed task |
| 4 | `validate-task-spec.sh` | Fails with a specific error when a placeholder is injected |
| 5 | `transition-status.sh` | `ready → in-progress` updates status and keeps file in `tasks/` |
| 6 | `transition-status.sh` | `in-progress → done` moves file to `tasks/done/` |
| 7 | `rebuild-state.sh` | Rebuilds `_state.yaml` and reflects the correct status |
| 8 | `list-ready.sh` | Excludes done tasks from the ready queue |
| 9 | `archive.sh` | Is a no-op when all done/parked tasks are already archived |
| 10 | `backup-backlog.sh` | Creates a `.tar.gz` archive in the requested directory |

## Isolation strategy

The scripts operate relative to the current working directory and do not accept a
`--root` override. The self-test therefore:

1. Creates a temp directory (`mktemp -d`).
2. `cd`s into it and runs `git init` so `validate-task-spec.sh` can resolve a
   repository root for path lookups.
3. Calls the skill scripts via absolute paths; their internal `SKILL_DIR` lookup
   still finds templates and sibling scripts correctly.
4. Uses `trap 'rm -rf "$TMPDIR"' EXIT` so cleanup happens even on early failure.

## macOS compatibility

`transition-status.sh` uses `flock(1)` (from `util-linux`), which is not present on
macOS. The self-test detects the missing binary and prepends a minimal shim to
`PATH`. The shim is safe because the test environment is single-threaded with no
concurrent access.
