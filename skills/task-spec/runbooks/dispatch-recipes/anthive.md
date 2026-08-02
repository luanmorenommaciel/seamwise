# Dispatch Recipe: anthive

> **Use when:** `execution_backend: anthive` — fan a spec (or several) out to parallel anthive sessions, then collect `output_artifacts:` declared in the frontmatter for downstream consumers.

anthive's distinguishing feature is parallel-session dispatch: a single spec can be replayed N times for comparison runs, or N sibling specs can run concurrently. The recipe handles both modes.

---

## Prerequisites

- `anthive` CLI installed and authenticated (`anthive whoami` returns your workspace).
- Spec is at `signed_off: true` with the gate clean.
- The spec declares an `output_artifacts:` block listing files the dispatcher should capture (e.g. test logs, perf traces, generated diffs).
- Sufficient API budget for the requested concurrency (anthive does not throttle silently).
- Working tree clean.

---

## Dispatch command

Single-session dispatch:

```bash
anthive run --spec tasks/T-<spec>.md
```

Parallel dispatch (N concurrent sessions on the same spec, for comparison):

```bash
anthive run --spec tasks/T-<spec>.md --replicas 3 --collect ./runs/
```

Batch dispatch across multiple specs:

```bash
anthive batch --glob 'tasks/T-2026*.md' --concurrency 4
```

After the runs complete, anthive deposits each replica's `output_artifacts:` into a per-run subdirectory under `./runs/<run-id>/`.

---

## Status reporting

anthive flips `status:` per spec, but parallel-replica runs require disambiguation. The CLI writes a per-run JSON to `./runs/<run-id>/result.json`:

```bash
anthive status                          # All active sessions
anthive status --run-id <id>            # Specific run
jq '.status' ./runs/<run-id>/result.json
```

The spec's `status:` reflects the **majority** verdict across replicas; ties default to `parked` and require human disambiguation.

---

## Failure modes

| Symptom | Action |
|---------|--------|
| `anthive: no output_artifacts declared` | Spec missing the `output_artifacts:` block — re-author and re-stamp |
| Replicas disagree (split verdict) | Inspect each `result.json`; the disagreement itself is signal — escalate to human review |
| API budget exhausted mid-batch | Park remaining specs with `blocked_reason: api-budget`; resume after top-up |
| `output_artifacts` files missing post-run | Check the run-id subdir's stderr.log; common cause is artifact path outside `touches_paths` |
| Session times out | Increase per-session `--timeout`; split the spec if the task is genuinely too large |

---

## See also

- [../dispatching-a-task-spec.md](../dispatching-a-task-spec.md) — router and pre-flight checklist
- [taskship.md](taskship.md) — sibling agentic runtime without parallel-replica semantics
- [../../references/concepts/agent-contract.md](../../references/concepts/agent-contract.md) — anthive honors read-zone semantics
- [../../references/concepts/signed-off.md](../../references/concepts/signed-off.md) — autonomy contract
