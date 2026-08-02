# Runbook: Recovering from a Crash

> **Use when:** Agent crashed mid-execution, state may be inconsistent.

## Symptoms

- `tasks/_state.yaml` doesn't match what `ls tasks/` shows
- A task shows `status: in-progress` but no agent is running
- Lock file `tasks/.state.lock` exists but no process holds it
- `_metrics.jsonl` has `iteration_start` with no `iteration_end`

## The recovery sequence

### Step 1 — Identify the stale task(s)

```bash
# Tasks claiming "in-progress" but no recent metrics
for f in tasks/T-*.md; do
  STATUS=$(grep '^status:' "$f" | awk '{print $2}')
  if [[ "$STATUS" == "in-progress" ]]; then
    ID=$(grep '^id:' "$f" | awk '{print $2}')
    LAST=$(grep "\"task\":\"$ID\"" tasks/_metrics.jsonl | tail -1)
    echo "$ID: last event: $LAST"
  fi
done
```

If `last event` was over an hour ago, the task is likely stale.

### Step 2 — Release stale locks

```bash
# Lock file exists but no process holds it
if [[ -f tasks/.state.lock ]]; then
  rm tasks/.state.lock
  echo "Released stale lock"
fi
```

flock automatically releases when the holding process exits, so the lock file
itself is usually harmless. Removing it is cleanup, not recovery.

### Step 3 — Inspect the metrics ledger

```bash
# What happened to the stale task?
grep "\"task\":\"T-XXX\"" tasks/_metrics.jsonl | tail -20
```

Look for the last successful eval result. That tells you how far the agent got.

### Step 4 — Decide: resume or park?

| If the agent | Then |
|--------------|------|
| Got most evals passing | Resume — transition back to ready, let next executor pick up |
| Was clearly stuck (no progress) | Park with reason="crashed; needs human triage" |
| Completed all evals but didn't finalize | Manually transition to done |

### Step 5 — Execute the transition

```bash
# Resume
bash ~/.claude/skills/task-spec/scripts/transition-status.sh T-XXX ready "recovered after crash"

# Or park
bash ~/.claude/skills/task-spec/scripts/transition-status.sh T-XXX parked "crashed at iteration N"

# Or finalize
bash ~/.claude/skills/task-spec/scripts/transition-status.sh T-XXX done "completed before crash"
```

### Step 6 — Rebuild state

```bash
bash ~/.claude/skills/task-spec/scripts/rebuild-state.sh
```

Forces `_state.yaml` to converge with frontmatter (the truth).

### Step 7 — Add a recovery note to metrics

```bash
TS=$(date -u +%FT%TZ)
echo "{\"ts\":\"$TS\",\"task\":\"T-XXX\",\"event\":\"recovered\",\"reason\":\"agent crashed; manual recovery\"}" >> tasks/_metrics.jsonl
```

Keeps the forensic record honest.

## Catastrophic recovery (whole tasks/ folder lost)

```bash
# Restore from git
git checkout HEAD -- tasks/

# OR from backup
tar xzf ~/Backups/backlog-YYYYMMDD.tar.gz

# Rebuild state
bash ~/.claude/skills/task-spec/scripts/rebuild-state.sh
```

The 5-layer architecture (git + folder + frontmatter + state.yaml + metrics.jsonl)
means even total data loss is recoverable to the last commit or backup.

## Prevention

- Run `backup-backlog.sh` via daily cron
- Commit task files immediately after generation
- Use the transition scripts (don't edit frontmatter directly)

Crashes happen. The architecture handles them. Recovery should be 5 minutes, not 5 hours.
