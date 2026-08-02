# Pattern: Atomic Status Transitions

> **Purpose**: The transition protocol — how statuses change without races, drift, or loss.
> **MCP Validated**: 2026-05-19

## The protocol

A status transition is a 7-step atomic operation. ALL 7 succeed or ALL 7 roll back.

```text
1. ACQUIRE lock (flock on _state.yaml.lock)
2. READ current status from frontmatter
3. VALIDATE transition is legal (status state machine)
4. UPDATE frontmatter in T-*.md (Layer 3 — truth)
5. MOVE file to correct location (active / done/ / parked/)
6. APPEND to _metrics.jsonl (Layer 5 — ledger)
7. TRIGGER _state.yaml rebuild (Layer 4 — index)
8. RELEASE lock
```

This is implemented by `scripts/transition-status.sh`. Never edit frontmatter directly.

## The state machine

```text
       ready
       ╱   ╲
      ╱     ╲
 in-progress  blocked
      │         │
   ┌──┴──┐      │ (when unblock condition met)
   │     │      │
  done parked   └──→ ready
```

| From | To | Allowed | When |
|------|----|---------|------|
| ready | in-progress | ✅ | Executor claims |
| ready | blocked | ✅ | Dependency discovered late |
| in-progress | done | ✅ | All evals pass |
| in-progress | parked | ✅ | Budget exhausted |
| in-progress | blocked | ✅ | Environment broken |
| blocked | ready | ✅ | Dependency satisfied |
| done | * | ❌ | Done is terminal |
| parked | ready | ✅ | Manual resurrection |
| parked | * | ❌ | Otherwise parked is terminal |

Invalid transitions (e.g., `done` → `in-progress`) are rejected by `transition-status.sh`.

## Why atomic matters

Without atomicity, race conditions happen:

```text
Agent A: reads status=ready
Agent B: reads status=ready
Agent A: sets status=in-progress
Agent B: sets status=in-progress   ← race! both think they have the task
```

With flock-guarded atomicity:

```text
Agent A: acquires lock
Agent A: reads + sets + commits
Agent A: releases lock
Agent B: acquires lock
Agent B: reads status=in-progress
Agent B: sees task is taken; returns gracefully
```

## Recovery from incomplete transitions

If a process crashes mid-transition, the flock releases automatically. The state
may be partially-written:

| What could be left over | Recovery |
|------------------------|----------|
| Frontmatter updated, file not moved | Run `archive.sh` to move done/parked tasks |
| File moved, metrics not logged | Manually append a metrics entry with reason="recovered" |
| _state.yaml out of sync | Run `rebuild-state.sh` to regenerate from frontmatter |

The 5-layer architecture (see `backlog-architecture.md`) ensures every failure
mode is recoverable.

## Why frontmatter is authoritative

When `_state.yaml` says one thing and the frontmatter says another, **the
frontmatter wins**. Always.

Reason: the frontmatter is co-located with the task content. Editing the file
and editing the status happen in the same git history entry. `_state.yaml` is
derived; it can be regenerated. The file is the source.

## Related

- [backlog-architecture.md](../concepts/backlog-architecture.md) — the 5 layers
- [agent-contract.md](../concepts/agent-contract.md) — when agents trigger transitions
- [../../runbooks/recovering-from-crash.md](../../runbooks/recovering-from-crash.md) — operational recovery
