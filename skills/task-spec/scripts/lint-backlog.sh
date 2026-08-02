#!/usr/bin/env bash
# lint-backlog.sh — Cross-task linter for the task-spec backlog.
#
# Detects:
#   (a) touches_paths overlaps between active (non-parked, non-archive) tasks
#   (b) depends_on cycles via tsort (with pure-bash fallback)
#   (b2) depends_on referencing a non-existent task (dangling DAG edge)
#   (c) duplicate id values across the backlog
#   (d) stale precondition references
#
# Usage:
#   bash lint-backlog.sh [--help]
#
# Exit codes:
#   0 — no issues
#   1 — one or more issues found

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./_lib.sh
source "$SCRIPT_DIR/_lib.sh"
ts_version_flag "$@"
ts_require_bash4 "$@"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  echo "Usage: bash lint-backlog.sh [--help]"
  echo ""
  echo "Cross-task linter for the task-spec backlog. Detects:"
  echo "  - touches_paths overlaps between active tasks"
  echo "  - depends_on cycles"
  echo "  - depends_on referencing a non-existent task"
  echo "  - duplicate task IDs"
  echo "  - stale precondition references"
  echo ""
  echo "Output: one line per issue. Exits non-zero if any issues are found."
  exit 0
fi

# Resolve the backlog to an ABSOLUTE path before moving anywhere. The cd below
# assumes the backlog hangs off the git root; in a nested workspace (a proving
# ground, a monorepo package) it does not, and a relative TASKSPEC_BACKLOG_DIR
# silently stops resolving the moment we leave the invocation directory.
if [[ -d "$TASKSPEC_BACKLOG_DIR" ]]; then
  TASKSPEC_BACKLOG_DIR="$(cd "$TASKSPEC_BACKLOG_DIR" && pwd)"
  export TASKSPEC_BACKLOG_DIR
fi
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && git rev-parse --show-toplevel 2>/dev/null || echo "$SCRIPT_DIR/../../..")"
cd "$REPO_ROOT"

# Data structures
# task_status[id] = status
# task_file[id] = filepath
# task_touches[id] = "path1 path2 ..."
# task_depends[id] = "dep1 dep2 ..."
# task_precondition[id] = "precondition text"
declare -A task_status
declare -A task_file
declare -A task_touches
declare -A task_creates
declare -A task_depends
declare -A task_precondition

# List of all task IDs
declare -a all_ids=()

# Helper: extract frontmatter from a file (delegates to the shared _lib.sh
# implementation — single source of truth, was previously a verbatim copy).
extract_frontmatter() {
  ts_frontmatter "$1"
}

# Helper: parse YAML list from frontmatter block
parse_yaml_list() {
  local key="$1"
  local block="$2"
  local line
  line=$(echo "$block" | grep "^${key}:" | head -1 || true)
  if [[ -z "$line" ]]; then
    return 0
  fi
  if echo "$line" | grep -qE '\['; then
    local result
    result=$(echo "$line" | sed -n 's/.*\[\(.*\)\].*/\1/p' | tr ',' '\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' || true)
    echo "$result" | grep -v '^$' || true
  elif echo "$line" | grep -qE "^${key}:[[:space:]]*$"; then
    echo "$block" | sed -n "/^${key}:/,/^[^ #]/p" | tail -n +2 | sed '/^[^ ]/d' | sed 's/^[[:space:]]*-[[:space:]]*//' | grep -v '^$' || true
  fi
  return 0
}

# Discover all task files
mapfile -t task_files < <(find "$TASKSPEC_BACKLOG_DIR" -name 'T-*.md' -type f 2>/dev/null | sort)

if [[ ${#task_files[@]} -eq 0 ]]; then
  echo "No task files found in $TASKSPEC_BACKLOG_DIR/"
  exit 0
fi

# Parse all task files
for f in "${task_files[@]}"; do
  fm=$(extract_frontmatter "$f")
  id=$(echo "$fm" | grep "^id:" | head -1 | awk '{print $2}' || true)
  status=$(echo "$fm" | grep "^status:" | head -1 | awk '{print $2}' || true)
  
  if [[ -z "$id" ]]; then
    echo "WARNING: $f missing id field"
    continue
  fi
  
  task_status[$id]="${status:-unknown}"
  task_file[$id]="$f"
  all_ids+=("$id")
  
  # The WRITE SURFACE is touches_paths PLUS creates_paths.
  #
  # This checked touches_paths alone, and every greenfield task declares its
  # writes in creates_paths — so on a backlog of nine such specs the overlap
  # check had literally nothing to look at and exited 0 in silence. The property
  # it exists to protect is "no two tasks write the same file", and for new files
  # that is precisely creates_paths. Two tasks both CREATING one path is the
  # worse case of the two: they do not merely contend, they both claim authorship.
  touches=$(parse_yaml_list "touches_paths" "$fm")
  creates=$(parse_yaml_list "creates_paths" "$fm")
  if [[ -n "$creates" ]]; then
    task_creates[$id]="$creates"
    touches=$(printf '%s\n%s' "$touches" "$creates" | grep -v '^$' || true)
  fi
  if [[ -n "$touches" ]]; then
    task_touches[$id]="$touches"
  fi
  
  deps=$(parse_yaml_list "depends_on" "$fm")
  if [[ -n "$deps" ]]; then
    task_depends[$id]="$deps"
  fi
  
  # Extract precondition text
  pc_line=$(echo "$fm" | grep "^precondition:" | head -1 || true)
  if [[ -n "$pc_line" ]]; then
    pc_text=$(echo "$pc_line" | sed 's/^precondition:[[:space:]]*//' | sed 's/^"//;s/"$//;s/^'"'"'//;s/'"'"'$//')
    task_precondition[$id]="$pc_text"
  fi
done

ERRORS=0
WARNINGS=0

# ---------------------------------------------------------------------------
# Check (a): touches_paths overlaps between active tasks
# ---------------------------------------------------------------------------
# Build map: path -> "id1 id2 ..."
declare -A path_owners

for id in "${all_ids[@]}"; do
  status=${task_status[$id]}
  f=${task_file[$id]}
  
  # Skip parked tasks and archive tasks for overlap detection
  if [[ "$status" == "parked" ]]; then
    continue
  fi
  if [[ "$f" == "$TASKSPEC_BACKLOG_DIR"/archive/* ]]; then
    continue
  fi
  
  touches=${task_touches[$id]:-}
  if [[ -z "$touches" ]]; then
    continue
  fi
  
  while IFS= read -r path; do
    [[ -z "$path" ]] && continue
    if [[ -z "${path_owners[$path]+x}" ]]; then
      path_owners[$path]="$id"
    else
      path_owners[$path]="${path_owners[$path]} $id"
    fi
  done <<< "$touches"
done

# Determine if a path is a code/script file
code_exts='\.(sh|py|js|ts|go|rs|java|rb|pl|c|cpp|h|hpp|cs|swift|kt|scala|r|m|mm|lua|vim|ps1|bat|cmd|php|tcl|awk|sed)$'

for path in "${!path_owners[@]}"; do
  owners=${path_owners[$path]}
  count=$(echo "$owners" | wc -w | tr -d ' ')
  
  if [[ "$count" -gt 1 ]]; then
    # Filter out any parked/archive owners that might have slipped in
    active_owners=""
    for owner in $owners; do
      owner_status=${task_status[$owner]}
      owner_file=${task_file[$owner]}
      if [[ "$owner_status" != "parked" && "$owner_file" != "$TASKSPEC_BACKLOG_DIR"/archive/* ]]; then
        if [[ -z "$active_owners" ]]; then
          active_owners="$owner"
        else
          active_owners="$active_owners $owner"
        fi
      fi
    done
    
    active_count=$(echo "$active_owners" | wc -w | tr -d ' ')
    if [[ "$active_count" -gt 1 ]]; then
      # Two tasks CREATING the same path is never merely a contention warning:
      # both claim authorship, so whichever runs second either clobbers the first
      # or fails. That is an ERROR regardless of file extension.
      dual_create=0
      for owner in $active_owners; do
        oc=${task_creates[$owner]:-}
        if [[ -n "$oc" ]] && printf '%s\n' "$oc" | grep -Fxq "$path"; then
          dual_create=$((dual_create + 1))
        fi
      done
      if [[ "$dual_create" -gt 1 ]]; then
        echo "ERROR: creates_paths collision on '$path' — authored by: $active_owners"
        echo "       Two tasks cannot both create one file; they cannot run concurrently."
        ERRORS=$((ERRORS + 1))
      elif echo "$path" | grep -qiE "$code_exts"; then
        echo "ERROR: write-surface overlap on '$path' between tasks: $active_owners"
        ERRORS=$((ERRORS + 1))
      else
        echo "WARNING: write-surface overlap on '$path' between tasks: $active_owners"
        WARNINGS=$((WARNINGS + 1))
      fi
    fi
  fi
done

# ---------------------------------------------------------------------------
# Check (a2): the concurrency partition — who may run beside whom
# ---------------------------------------------------------------------------
# A swimlane decomposition earns its keep by producing WRITE-DISJOINT groups: if
# no two lanes write the same prefix, their tasks can be dispatched in parallel
# with no merge conflict BY CONSTRUCTION rather than by hoping. That property was
# a convention nobody checked. Reporting it turns the design discipline into
# something an operator (or a fleet manager) can read and rely on.
#
# The prefix is depth 2 (`cvg/capture`, `cvg/serve`), which is the granularity a
# swimlane actually owns. Deeper would report per-directory noise; shallower
# would collapse every lane into one group.
declare -A prefix_tasks
for id in "${all_ids[@]}"; do
  [[ "${task_status[$id]}" == "parked" ]] && continue
  surface=${task_touches[$id]:-}
  [[ -z "$surface" ]] && continue
  while IFS= read -r path; do
    [[ -z "$path" ]] && continue
    pfx=$(printf '%s' "$path" | awk -F/ 'NF>=2{print $1"/"$2} NF<2{print $1}')
    case " ${prefix_tasks[$pfx]:-} " in
      *" $id "*) : ;;
      *) prefix_tasks[$pfx]="${prefix_tasks[$pfx]:-} $id" ;;
    esac
  done <<< "$surface"
done
if [[ ${#prefix_tasks[@]} -gt 0 ]]; then
  echo "concurrency partition (write-disjoint groups — safe to dispatch together):"
  for pfx in $(printf '%s\n' "${!prefix_tasks[@]}" | sort); do
    # shellcheck disable=SC2086
    set -- ${prefix_tasks[$pfx]}
    echo "  $pfx  ($# task(s)):$(printf ' %s' "$@")"
  done
  # A task whose surface spans two prefixes is the one that breaks the partition
  # — it is the reason a "parallel by lane" dispatch would conflict, so name it.
  for id in "${all_ids[@]}"; do
    surface=${task_touches[$id]:-}
    [[ -z "$surface" ]] && continue
    spans=$(printf '%s\n' "$surface" | awk -F/ 'NF>=2{print $1"/"$2} NF<2{print $1}' | sort -u | wc -l | tr -d ' ')
    if [[ "$spans" -gt 1 ]]; then
      echo "  NOTE: $id writes across $spans prefixes — it cannot ride a single lane."
    fi
  done
fi

# ---------------------------------------------------------------------------
# Check (b2): depends_on referencing a non-existent task (dangling DAG edge)
# ---------------------------------------------------------------------------
# The tsort/DFS edge-builders below only add an edge when BOTH endpoints exist
# (the '${task_file[$dep]+x}' guard), which means a depends_on pointing at a task
# that is not in the backlog is silently DROPPED and never surfaced. Report it
# here so a typo'd or purged dependency is caught at the backlog level (the
# per-file validator already catches it for a single spec; this is the cross-task
# net). Additive: does not alter the edge-building or cycle logic below.
for id in "${all_ids[@]}"; do
  deps=${task_depends[$id]:-}
  [[ -z "$deps" ]] && continue
  for dep in $deps; do
    [[ -z "$dep" ]] && continue
    if [[ -z "${task_file[$dep]+x}" ]]; then
      echo "ERROR: depends_on references non-existent task: '$dep' (declared by $id)"
      ERRORS=$((ERRORS + 1))
    fi
  done
done

# ---------------------------------------------------------------------------
# Check (b): depends_on cycles
# ---------------------------------------------------------------------------
# Build adjacency list for tsort
tsort_input=$(mktemp)
tsort_nodes=$(mktemp)

for id in "${all_ids[@]}"; do
  deps=${task_depends[$id]:-}
  echo "$id" >> "$tsort_nodes"
  if [[ -n "$deps" ]]; then
    for dep in $deps; do
      # Only include edges where both nodes exist
      if [[ -n "${task_file[$dep]+x}" ]]; then
        echo "$dep $id" >> "$tsort_input"
        echo "$dep" >> "$tsort_nodes"
      fi
    done
  fi
done

# tsort approach
if command -v tsort >/dev/null 2>&1; then
  tsort_err=$(tsort "$tsort_input" 2>&1 >/dev/null) || true
  if echo "$tsort_err" | grep -qi "cycle"; then
    cycle_line=$(echo "$tsort_err" | grep -i "cycle" | head -1)
    # NOTE: 'grep -v ^tsort:' matches NOTHING for a pure cycle (every tsort line
    # is 'tsort:'-prefixed), returning exit 1. As a standalone assignment under
    # 'set -euo pipefail' that aborted the whole script BEFORE the echo below —
    # so cycles were detected (rc=1) but reported SILENTLY. The trailing '|| true'
    # neutralises the empty-match exit so the ERROR line always prints.
    cycle_nodes=$(echo "$tsort_err" | grep -v "^tsort:" | head -5 | tr '\n' ' ' || true)
    echo "ERROR: depends_on cycle detected ($cycle_line) involving: $cycle_nodes"
    ERRORS=$((ERRORS + 1))
  fi
else
  # Pure bash fallback: DFS cycle detection
  declare -A adj
  for id in "${all_ids[@]}"; do
    deps=${task_depends[$id]:-}
    adj[$id]="$deps"
  done
  
  cycle_found=0
  for start in "${all_ids[@]}"; do
    [[ $cycle_found -eq 1 ]] && break
    declare -A visited=()
    declare -A recstack=()
    
    dfs() {
      local node=$1
      visited[$node]=1
      recstack[$node]=1
      local neighbors=${adj[$node]:-}
      for neighbor in $neighbors; do
        [[ -z "${task_file[$neighbor]+x}" ]] && continue
        if [[ -z "${visited[$neighbor]+x}" ]]; then
          dfs "$neighbor"
          [[ $cycle_found -eq 1 ]] && return
        elif [[ "${recstack[$neighbor]:-0}" == "1" ]]; then
          echo "ERROR: depends_on cycle detected involving $neighbor"
          cycle_found=1
          return
        fi
      done
      recstack[$node]=0
    }
    
    dfs "$start"
  done
  
  if [[ $cycle_found -eq 1 ]]; then
    ERRORS=$((ERRORS + 1))
  fi
fi

rm -f "$tsort_input" "$tsort_nodes"

# ---------------------------------------------------------------------------
# Check (c): duplicate IDs
# ---------------------------------------------------------------------------
declare -A id_files

for id in "${all_ids[@]}"; do
  f=${task_file[$id]}
  if [[ -z "${id_files[$id]+x}" ]]; then
    id_files[$id]="$f"
  else
    id_files[$id]="${id_files[$id]} $f"
  fi
done

for id in "${!id_files[@]}"; do
  files=${id_files[$id]}
  count=$(echo "$files" | wc -w | tr -d ' ')
  if [[ "$count" -gt 1 ]]; then
    echo "ERROR: duplicate id '$id' found in files: $files"
    ERRORS=$((ERRORS + 1))
  fi
done

# ---------------------------------------------------------------------------
# Check (d): stale precondition references
# ---------------------------------------------------------------------------
for id in "${all_ids[@]}"; do
  pc=${task_precondition[$id]:-}
  [[ -z "$pc" ]] && continue
  
  status=${task_status[$id]}
  
  # Extract path-like tokens from precondition text
  path_tokens=$(echo "$pc" | grep -oE '[a-zA-Z0-9_.][a-zA-Z0-9_./-]*' | grep '/' | grep -v '://' | sort -u || true)
  
  while IFS= read -r token; do
    [[ -z "$token" ]] && continue
    
    # Resolve relative to repo root
    if [[ -e "$token" ]]; then
      # Path exists — if task is active, precondition may be stale
      if [[ "$status" == "ready" || "$status" == "in-progress" || "$status" == "blocked" ]]; then
        echo "WARNING: stale precondition in $id: referenced path exists, work may be unblocked: $token"
        WARNINGS=$((WARNINGS + 1))
      fi
    else
      # Path does not exist — if task is done, the precondition was never met
      if [[ "$status" == "done" ]]; then
        echo "WARNING: stale precondition in $id: referenced path missing for done task: $token"
        WARNINGS=$((WARNINGS + 1))
      fi
    fi
  done <<< "$path_tokens"
done

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
if [[ $ERRORS -gt 0 || $WARNINGS -gt 0 ]]; then
  exit 1
fi

exit 0
