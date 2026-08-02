# Backlog Architecture — The 5-Layer Model

> How Task-Spec files survive crashes, races, and orphaned state.
> The state-management model that backs every Task-Spec workflow.

---

## The problem this solves

Every autonomous task system quietly fails at one of four points:

| Failure | How it happens |
|---------|---------------|
| **Lost tasks** | Agent crashes mid-write; T-*.md never lands; user forgets the request |
| **Stale status** | Task marked `ready` but actually `in-progress` by another agent |
| **Race conditions** | Two agents claim the same task simultaneously |
| **Orphaned state** | `_state.yaml` says done; T-*.md says blocked; nobody knows the truth |

The 5-layer architecture prevents all four.

---

## The 5 layers

```text
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1 — git (source of truth)                            │
│  Every T-*.md is committed. git log = audit trail.          │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  LAYER 2 — tasks/ folder (the backlog itself)               │
│  Active T-*.md / done/ / parked/ subdirs                    │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  LAYER 3 — frontmatter status (per-file truth)              │
│  YAML `status:` field IS the canonical status               │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  LAYER 4 — tasks/_state.yaml (derived index)                │
│  Aggregated view. REBUILDABLE from frontmatter.             │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  LAYER 5 — tasks/_metrics.jsonl (append-only ledger)        │
│  One JSONL line per state event. Never edited.             │
└─────────────────────────────────────────────────────────────┘
```

Read it as: **git stores everything, the file is the truth, the index is rebuildable, the ledger is forensic.**

---

## Layer 1 — git

### Purpose

Permanent record. Survives drive failure, accidental deletion, malicious tampering.

### Rules

- Every new T-*.md is committed immediately by `scripts/generate-task-spec.sh`
- Status transitions are committed
- Moves to `done/` and `parked/` are git operations (history preserved)
- `_state.yaml` is committed (snapshot of derived state)
- `_metrics.jsonl` is committed (the forensic record)

### Operations

```bash
# After creating a task
git add tasks/T-${DATE}-${SLUG}.md
git commit -m "task: ${TITLE}"

# After status transition
git add tasks/T-${ID}.md tasks/_state.yaml tasks/_metrics.jsonl
git commit -m "task: ${ID} → ${NEW_STATUS}"

# Recovery: re-clone the repo
git clone <url>
# Backlog is exactly as it was
```

### Why this matters

Without git, an `rm tasks/` ends your backlog. With git, it's recoverable in
seconds.

---

## Layer 2 — tasks/ folder structure

### Directory layout

```text
tasks/
├── T-20260519-foo.md                  ← active backlog (ready | in-progress | blocked)
├── T-20260519-bar.md
├── done/
│   ├── T-20260518-baz.md              ← completed
│   └── T-20260517-qux.md
├── parked/
│   ├── T-20260516-blocked-by-dep.md   ← budget exhausted OR blocked with context
│   └── T-20260515-deferred.md
├── _state.yaml                        ← derived index
└── _metrics.jsonl                     ← append-only ledger
```

### Conventions

| Location | Status values allowed |
|----------|----------------------|
| `tasks/T-*.md` (root) | `ready`, `in-progress`, `blocked` |
| `tasks/done/T-*.md` | `done` |
| `tasks/parked/T-*.md` | `parked` |

Moving a task between subdirs is itself a status transition and follows the
atomic transition protocol.

### Why this matters

`ls tasks/` shows you exactly what's actionable. No filtering. No querying. The
filesystem IS the query.

---

## Layer 3 — frontmatter status (per-file truth)

### Authoritative source

The `status:` field in each Task-Spec's YAML frontmatter is the **single source
of truth** for that task's state. Layer 4 (`_state.yaml`) and Layer 5
(`_metrics.jsonl`) derive from this.

```yaml
---
id: T-20260519-foo
status: in-progress    # ← authoritative
...
---
```

### Rules

- Status changes happen via `scripts/transition-status.sh` (atomic + logged)
- Direct editing of frontmatter is allowed only for `tags`, `owner`, and similar
  non-state fields
- Two agents must NEVER write to the same T-*.md frontmatter simultaneously
  (enforced by flock)

### Why this matters

If `_state.yaml` says "done" but the file says "blocked," the file wins. Always.
The file is the truth; the index is just an index.

---

## Layer 4 — _state.yaml (derived index)

### Purpose

Fast queries without scanning every file. "What's ready?" should be O(1), not
O(n).

### Schema

```yaml
schema_version: 1
last_rebuilt: 2026-05-19T16:42:00Z

tasks:
  T-20260519-foo:
    status: ready
    effort: S
    agent: any
    depends_on: []
    touches_paths: [docs/foo.md]
    location: tasks/T-20260519-foo.md
  T-20260518-bar:
    status: done
    effort: M
    location: tasks/done/T-20260518-bar.md

ready_queue:
  - T-20260519-foo

in_progress:
  - T-20260519-quux

blocked:
  - T-20260519-baz: waiting_on T-20260517-prereq

stats:
  total: 4
  ready: 1
  in_progress: 1
  blocked: 1
  done: 1
  parked: 0
```

### Critical property

**`_state.yaml` is REBUILDABLE.** Run `scripts/rebuild-state.sh` and it scans
every T-*.md frontmatter, regenerates the index. If `_state.yaml` ever gets
corrupted, lost, or out-of-sync: regenerate it.

### Rules

- Writes use `flock` to prevent concurrent modification
- After every status transition, `_state.yaml` is updated
- A nightly cron may run `rebuild-state.sh` defensively to catch drift

### Why this matters

Multi-agent systems need a query layer. Without `_state.yaml`, "find me ready
tasks not blocked on anything" requires scanning every file. With it, the answer
is one YAML read.

---

## Layer 5 — _metrics.jsonl (append-only ledger)

### Purpose

Forensic record of EVERY state change. Survives crashes. Answers "what
happened?"

### Format

One JSON object per line. Newline-delimited.

```jsonl
{"ts":"2026-05-19T14:00:00Z","task":"T-20260519-foo","event":"created","author":"luan","source":"meeting-2026-05-19"}
{"ts":"2026-05-19T14:05:00Z","task":"T-20260519-foo","event":"status_change","from":"ready","to":"in-progress","agent":"claude-opus-4-7"}
{"ts":"2026-05-19T14:05:15Z","task":"T-20260519-foo","event":"iteration_start","iteration":1,"agent":"claude-opus-4-7"}
{"ts":"2026-05-19T14:06:30Z","task":"T-20260519-foo","event":"eval_result","iteration":1,"eval_id":"eval_1","status":"pass","duration_ms":4200}
{"ts":"2026-05-19T14:06:35Z","task":"T-20260519-foo","event":"eval_result","iteration":1,"eval_id":"eval_2","status":"fail","duration_ms":1100,"output":"connection refused"}
{"ts":"2026-05-19T14:06:36Z","task":"T-20260519-foo","event":"iteration_end","iteration":1,"result":"retry_with_reason","reason":"eval_2 failed: connection refused"}
{"ts":"2026-05-19T14:07:00Z","task":"T-20260519-foo","event":"iteration_start","iteration":2,"agent":"claude-opus-4-7"}
{"ts":"2026-05-19T14:09:42Z","task":"T-20260519-foo","event":"all_evals_passed","iteration":2,"tokens_in":12430,"tokens_out":3200,"cost_usd":0.42}
{"ts":"2026-05-19T14:09:43Z","task":"T-20260519-foo","event":"status_change","from":"in-progress","to":"done"}
{"ts":"2026-05-19T14:09:44Z","task":"T-20260519-foo","event":"archived","to":"tasks/done/T-20260519-foo.md"}
```

### Event types

| Event | Required fields | Purpose |
|-------|----------------|---------|
| `created` | `task`, `author`, `source` | Task entered the system |
| `status_change` | `task`, `from`, `to`, `agent` | Status transition |
| `iteration_start` | `task`, `iteration`, `agent` | New eval-loop iteration |
| `iteration_end` | `task`, `iteration`, `result` | Iteration completed |
| `eval_result` | `task`, `iteration`, `eval_id`, `status`, `duration_ms` | Single eval ran |
| `all_evals_passed` | `task`, `iteration`, `tokens_in/out`, `cost_usd` | Terminal success |
| `budget_exhausted` | `task`, `iteration`, `tokens_in/out`, `cost_usd` | Terminal failure |
| `archived` | `task`, `to` | File moved to subdir |
| `parked` | `task`, `reason` | Task parked with context |
| `blocked` | `task`, `waiting_on` | Task blocked on dependency |

### Rules

- **Append-only**. Never edit existing lines. Never delete lines.
- Each line is a complete JSON object (no multi-line entries)
- Timestamps in ISO8601 UTC
- The file may grow large; archive monthly to `_metrics.archive.YYYYMM.jsonl`

### Why this matters

If a process crashes mid-loop, the ledger captured every step up to the crash.
Replay it to reconstruct what happened. The flock-release-on-crash means even
hard kills leave the system recoverable.

---

## How the layers cooperate (the full transaction)

When an agent transitions `T-foo` from `ready` to `in-progress`:

```bash
# 1. Acquire lock (flock on _state.yaml)
exec 9>tasks/_state.yaml.lock
flock 9

# 2. Read current status from frontmatter (Layer 3)
CURRENT=$(grep '^status:' tasks/T-foo.md | awk '{print $2}')

# 3. Validate transition is legal
[[ "$CURRENT" == "ready" ]] || { flock -u 9; exit 1; }

# 4. Update frontmatter (Layer 3 — the truth)
sed -i.bak 's/^status: ready/status: in-progress/' tasks/T-foo.md
rm tasks/T-foo.md.bak

# 5. Update _state.yaml (Layer 4 — the index)
yq eval '.tasks["T-foo"].status = "in-progress"' -i tasks/_state.yaml

# 6. Append to _metrics.jsonl (Layer 5 — the ledger)
echo '{"ts":"'$(date -u +%FT%TZ)'","task":"T-foo","event":"status_change","from":"ready","to":"in-progress"}' >> tasks/_metrics.jsonl

# 7. Commit (Layer 1 — git)
git add tasks/T-foo.md tasks/_state.yaml tasks/_metrics.jsonl
git commit -m "task: T-foo → in-progress"

# 8. Release lock
flock -u 9
```

This is `scripts/transition-status.sh` in essence. All 8 steps OR all 8 rollback.

---

## Recovery scenarios

### Scenario 1 — `_state.yaml` corrupted

```bash
mv tasks/_state.yaml tasks/_state.yaml.broken
bash ~/.claude/skills/task-spec/scripts/rebuild-state.sh
# _state.yaml regenerated from frontmatter
```

### Scenario 2 — Frontmatter doesn't match `_state.yaml`

Frontmatter wins. Always.

```bash
bash ~/.claude/skills/task-spec/scripts/rebuild-state.sh
# Forces _state.yaml back into sync with frontmatter
```

### Scenario 3 — Agent crashed mid-iteration

```bash
# Read _metrics.jsonl tail for the task
grep '"task":"T-foo"' tasks/_metrics.jsonl | tail -5

# Last entry shows last-known state (iteration_start with no iteration_end)
# Manual intervention: either restart the loop or park the task with context
```

### Scenario 4 — Whole `tasks/` folder lost

```bash
git checkout HEAD -- tasks/
# Backlog fully restored
```

### Scenario 5 — Catastrophic data loss

```bash
# Restore from latest backup snapshot
tar xzf ~/Backups/backlog-2026-05-18.tar.gz
# Backlog restored to last snapshot; lost work since then
```

---

## Backup strategy (defense in depth)

Beyond git:

```bash
# scripts/backup-backlog.sh — run via cron daily at 03:00 local
tar czf ~/Backups/backlog-$(date +%Y%m%d).tar.gz \
    tasks/_state.yaml \
    tasks/_metrics.jsonl \
    tasks/

# Keep 30 days of snapshots
find ~/Backups -name 'backlog-*.tar.gz' -mtime +30 -delete
```

Git is the primary safety net. The tar snapshots are belt-and-suspenders for the
rare case git itself gets corrupted.

---

## What NOT to do

| Anti-pattern | Why it breaks the model |
|--------------|------------------------|
| Edit `_state.yaml` directly | Race conditions; bypasses lock; will desync from frontmatter |
| Skip the metrics ledger entry | Forensic record becomes lying; you can't trust it |
| Delete entries from `_metrics.jsonl` | Append-only is the guarantee; deletion breaks replay |
| Edit T-*.md without commit | Untracked changes lose to git checkout |
| Use a database instead of files | Defeats the whole point — files are the moat; databases are operational overhead |

---

## Why this model wins

Three properties no other backlog architecture has all of:

1. **File-system native** — works with git, tar, rsync, ssh, anything
2. **No external dependencies** — no database, no service, no API
3. **Forensically queryable** — `_metrics.jsonl` answers any state question via replay

These together make Task-Spec backlogs portable across machines, recoverable
from any failure mode, and auditable to the byte.

---

## See also

- [task-spec-v1.md](task-spec-v1.md) — the format that produces files in this backlog
- [../patterns/atomic-status-transitions.md](../patterns/atomic-status-transitions.md) — the transition protocol in detail
- [../../runbooks/recovering-from-crash.md](../../runbooks/recovering-from-crash.md) — concrete recovery walkthrough
