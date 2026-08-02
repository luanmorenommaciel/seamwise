# Pattern: Runnable Bash Evals

> **Purpose**: How to write Zone 2 success criteria that are terminal, idempotent, and explainable.
> **MCP Validated**: 2026-05-19

## The principles

Every eval must satisfy:

1. **Terminal** — returns deterministically (no infinite loops)
2. **Idempotent** — running twice gives the same result
3. **Cheap-before-expensive** — fail fast on simple checks
4. **Explainable** — one-line description of WHY it exists
5. **Bash-portable** — standard POSIX where possible; flag macOS/Linux differences

## Standard structure

```bash
# eval-N: <one-line description of what this verifies>
eval_N() {
  <commands>
}
```

Each function returns 0 (pass) or non-zero (fail). The shell exit code IS the contract.

## Common eval patterns

### Pattern 1 — Presence checks (cheapest, run first)

```bash
eval_1() {
  test -f docs/runbook.md
}
```

Use for: file exists, directory exists, script is executable.

### Pattern 2 — Content checks

```bash
eval_2() {
  grep -qi "rollback procedure" docs/runbook.md
}
```

Use for: required sections present, important phrases included.

### Pattern 3 — HTTP probes

```bash
eval_3() {
  curl -fs http://localhost:8000/health | jq -e '.status == "ok"' >/dev/null
}
```

Use for: services reachable, endpoints returning expected payloads.

### Pattern 4 — Test suite gates

```bash
eval_4() {
  pytest tests/test_new_module.py -q
}
```

Use for: new tests pass, regression suite still green.

### Pattern 5 — Docker / process state

```bash
eval_5() {
  docker ps --filter "name=myservice" --filter "health=healthy" | grep -q myservice
}
```

Use for: containers healthy, processes running.

### Pattern 6 — Schema / config validation

```bash
eval_6() {
  python -c "import yaml; yaml.safe_load(open('config.yaml'))" 2>/dev/null
}
```

Use for: YAML valid, JSON parses, schema matches.

### Pattern 7 — Behavioral probes

```bash
eval_7() {
  RESULT=$(curl -s -X POST http://localhost:8000/widgets -d '{"name":"test"}')
  echo "$RESULT" | jq -e '.id and .name == "test"' >/dev/null
}
```

Use for: actual API behavior (not just reachability).

## Ordering rule

Order evals cheap-to-expensive so the loop fails fast:

```bash
eval_1  # presence check          — 1ms
eval_2  # content check           — 10ms
eval_3  # static config validation — 100ms
eval_4  # HTTP probe              — 500ms
eval_5  # docker health check     — 5s
eval_6  # test suite              — 30s
eval_7  # behavioral integration  — 2min
```

Agent loops on the first failure. Cheap evals failing first = fast retry. Expensive evals are last-line-of-defense.

## Anti-patterns

### Wrong: flaky evals

```bash
# ❌ Network might be slow; flakes randomly
eval_X() {
  curl http://api.example.com/status | grep -q "ok"
}
```

Add timeout + retry:

```bash
# ✅ Bounded + explicit
eval_X() {
  for i in 1 2 3; do
    curl -fsm 5 http://api.example.com/status | grep -q "ok" && return 0
    sleep 2
  done
  return 1
}
```

### Wrong: non-idempotent evals

```bash
# ❌ First run creates a record; second run finds existing record
eval_X() {
  curl -X POST http://localhost/api/items -d '{"name":"test"}' | jq -e '.created'
}
```

Use idempotent operations or cleanup:

```bash
# ✅ Idempotent (uses PUT or upsert)
eval_X() {
  curl -X PUT http://localhost/api/items/test -d '{"name":"test"}' | jq -e '.id'
}
```

### Wrong: presence-without-behavior

```bash
# ❌ /health endpoint exists, returns 200 — but is empty
eval_X() {
  curl -fs http://localhost/health
}
```

Add content check:

```bash
# ✅ Endpoint exists AND returns correct payload
eval_X() {
  curl -fs http://localhost/health | jq -e '.status == "ok" and .version'
}
```

### Wrong: gaming the eval (Goodhart)

```bash
# Easy to game: agent makes ANY endpoint return 200
eval_X() {
  curl -fs http://localhost/api/widgets | jq -e 'type == "array"'
}
```

Defense: include behavioral evals that check actual semantics, not just shape.

## macOS vs Linux portability

```bash
# Use POSIX-compatible flags where possible
test -f X        # works everywhere
[[ -f X ]]       # bash-only (but standard for Task-Spec)

# Beware GNU vs BSD differences
sed -i ...       # GNU sed (Linux)
sed -i '' ...    # BSD sed (macOS)

# Prefer perl or awk for cross-platform text manipulation
```

When in doubt, test on both. Task-Spec evals run on whatever machine the agent uses.

## Runner + Validator integration

The `run-task-spec.sh` script is the execution harness for eval bodies. It:

- Extracts Success Criteria and Exit Check bash blocks from the task file
- Runs each `eval_N()` in a disposable subshell with `set -euo pipefail`
- Captures per-eval stdout/stderr/duration
- Reports `pass`/`fail` per eval with timing
- Runs the Exit Check and exits 0 only when it returns 0
- `--ci` emits one JSON line per eval for non-interactive pipelines

The `validate-task-spec.sh` script can perform two additional semantic checks on
your eval bodies (both opt-in):

1. **`--shellcheck-evals`** — extracts every bash block from the Success Criteria
   and Exit Check zones, writes them to a temp script, and runs
   `shellcheck -e SC2086,SC2034 -S warning`. This catches syntax errors,
   unreachable code, and unquoted variables at warning level or above.
   Hard-fails if `shellcheck` is not installed when the flag is explicitly requested.

2. **`--dry-run-eval`** — extracts the same bash blocks, combines them into a
   single disposable script, and sources them in a `(subshell)`. The Exit Check
   is executed against the current repo. If any eval returns non-zero, the
   validator reports the failure. This is the cheapest way to detect
   tautological or broken evals before they ship.

Both flags are off by default so the fast structural lint stays fast.

## The runner: `run-task-spec.sh`

While the validator checks structure, `run-task-spec.sh` executes the evals and
reports pass/fail. It is heredoc-aware: eval bodies that write fenced markdown
fixtures via heredocs (`cat <<EOF ... ```bash ... ``` ... EOF`) are extracted
correctly — inner `## headers` and ` ``` ` fences inside a heredoc never trip the
section or block boundary detection.

```bash
bash run-task-spec.sh <path/to/T-*.md>        # human-readable
bash run-task-spec.sh --ci <path/to/T-*.md>   # one JSON line per eval
```

### `--ci` JSON output schema

In `--ci` mode the runner emits **one JSON object per line** (JSONL). There are
three line shapes:

```jsonc
// 1. Per-eval result (one per eval_N defined in Success Criteria)
{"eval":"eval_1","status":"pass","duration_sec":1,"stdout":"PASS: ...","stderr":""}

// 2. Warning for an eval defined but not called in Exit Check
{"eval":"eval_4","status":"warn","message":"defined in Success Criteria but not called in Exit Check"}

// 3. Final Exit Check verdict (always last; the authoritative pass/fail)
{"eval":"_exit_check","status":"pass","duration_sec":2,"stdout":"...","stderr":""}

// Runner-level errors use the reserved eval name "_runner"
{"eval":"_runner","status":"fail","message":"file not found: T-x.md"}
```

| Field | Type | Meaning |
| ----- | ---- | ------- |
| `eval` | string | eval name, or reserved `_exit_check` / `_runner` |
| `status` | enum | one of `pass`, `fail`, `warn` |
| `duration_sec` | int | wall-clock seconds (omitted on `_runner` errors) |
| `stdout` / `stderr` | string | captured output (JSON-escaped) |
| `message` | string | present on `warn` and `_runner` lines |

Exit code: `0` only when `_exit_check` is `pass`; non-zero otherwise. Consumers
should treat the `_exit_check` line as the ground-truth verdict and the exit code
as its machine mirror.

## Related

- [task-spec-v1.md](../concepts/task-spec-v1.md) — Zone 2 format reference
- [validation-card-yaml.md](validation-card-yaml.md) — YAML mirror of evals
- [eval-driven-development.md](../concepts/eval-driven-development.md) — why evals matter
