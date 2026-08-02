#!/usr/bin/env bash
# run-task-spec.sh — Execute the evals from a Task-Spec file.
#
# Usage:
#   bash run-task-spec.sh [--ci] <path/to/T-*.md>
#
# Options:
#   --ci     Emit one JSON line per eval (non-interactive mode)
#
# Exit codes:
#   0 — Exit Check returned 0 (task evals pass)
#   1 — Exit Check returned non-zero, file not found, or parsing error

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./_lib.sh
source "$SCRIPT_DIR/_lib.sh"
ts_version_flag "$@"

CI_MODE=false
FILE=""

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --ci) CI_MODE=true; shift ;;
    --help|-h)
      echo "Usage: run-task-spec.sh [--ci] <path/to/T-*.md>"
      exit 0
      ;;
    --) shift; break ;;
    -*)
      if [[ "$CI_MODE" == true ]]; then
        echo '{"eval":"_runner","status":"fail","message":"unknown option: '"$1"'"}'
      else
        echo "Unknown option: $1" >&2
        echo "Usage: run-task-spec.sh [--ci] <path/to/T-*.md>" >&2
      fi
      exit 1
      ;;
    *)
      if [[ -z "$FILE" ]]; then
        FILE="$1"
      else
        if [[ "$CI_MODE" == true ]]; then
          echo '{"eval":"_runner","status":"fail","message":"too many arguments"}'
        else
          echo "Usage: run-task-spec.sh [--ci] <path/to/T-*.md>" >&2
        fi
        exit 1
      fi
      shift ;;
  esac
done

if [[ -z "$FILE" ]]; then
  if [[ "$CI_MODE" == true ]]; then
    echo '{"eval":"_runner","status":"fail","message":"path required"}'
  else
    echo "Usage: run-task-spec.sh [--ci] <path/to/T-*.md>" >&2
  fi
  exit 1
fi

if [[ ! -f "$FILE" ]]; then
  if [[ "$CI_MODE" == true ]]; then
    printf '%s\n' '{"eval":"_runner","status":"fail","message":"file not found: '"$FILE"'"}'
  else
    echo "FAIL: $FILE not found" >&2
  fi
  exit 1
fi

# Resolve git root
GIT_ROOT=$(cd "$(dirname "$FILE")" && git rev-parse --show-toplevel 2>/dev/null || echo "")

# WHERE THE EVALS ACTUALLY RUN
#
# A spec's relative paths ("cvg/capture/orders.py") are written against its own
# WORKSPACE, not against whatever repository happens to contain it. For a
# workspace nested inside a larger repo — or any run inside a git worktree —
# the git root is the wrong directory, and every `test -f` fails in 0s without
# ever reaching the work. That RED is indistinguishable from a real failure
# except by the suspiciously round duration.
#
# TASKSPEC_WORKSPACE_ROOT lets the caller state the workspace explicitly.
# Otherwise infer it: a spec at <ws>/tasks/ or <ws>/cvg/tasks/ means <ws>.
EVAL_CWD=""
if [ -n "${TASKSPEC_WORKSPACE_ROOT:-}" ] && [ -d "${TASKSPEC_WORKSPACE_ROOT}" ]; then
  EVAL_CWD="$(cd "$TASKSPEC_WORKSPACE_ROOT" && pwd)"
else
  # Shared resolver (ts_workspace_root in _lib.sh) — see the note there. The
  # previous inference required the spec's directory to be named exactly `tasks`,
  # so a spec in tasks/done/ skipped it entirely and fell through to GIT_ROOT.
  _cand="$(ts_workspace_root "$(dirname "$FILE")" 2>/dev/null || true)"
  [ -n "$_cand" ] && [ -d "$_cand" ] && EVAL_CWD="$_cand"
fi
[ -n "$EVAL_CWD" ] || EVAL_CWD="$GIT_ROOT"
if [[ -z "$GIT_ROOT" ]]; then
  if [[ "$CI_MODE" == true ]]; then
    echo '{"eval":"_runner","status":"fail","message":"not inside a git repository"}'
  else
    echo "FAIL: not inside a git repository" >&2
  fi
  exit 1
fi

# extract_bash_block — pull the bash from a named section's fenced ```bash block.
#
# G7 heredoc-safety: eval bodies routinely contain heredocs that write fenced
# markdown fixtures, e.g.:
#     cat > "$f" <<EOF
#     ## Success Criteria
#     ```bash
#     eval_1() { true; }
#     ```
#     EOF
# A naive extractor breaks two ways: (1) the inner `## Success Criteria` line trips
# section-boundary detection, truncating the section; (2) the inner ``` trips fence
# detection, truncating the bash block. This extractor is heredoc-aware: it tracks
# open heredoc delimiters (<<EOF, <<'EOF', <<-EOF, <<"EOF") and ignores ALL section
# headers and fences while inside a heredoc. Only fences/headers at the real shell
# level are honored.
#
# Args: $1 = section header text (lowercased match, e.g. "success criteria")
extract_bash_block() {
  local section="$1"
  awk -v want="$section" '
    function strip(s){ gsub(/^[ \t]+|[ \t]+$/, "", s); return s }
    BEGIN { in_section=0; in_block=0; hd=""; top_fence=0 }
    {
      line=$0
      lower=tolower(strip(line))

      # --- While capturing the target section bash block ---
      if (in_block) {
        # Inside a heredoc: nothing structural is honored until terminator.
        if (hd != "") {
          if (strip(line) == hd) { hd="" }
          print line
          next
        }
        if (line ~ /^```$/) { exit }   # real closing fence ends the block
        # Detect heredoc opener (<<EOF, <<-EOF, <<"EOF", <<'"'"'EOF'"'"').
        if (match(line, /<<-?[ \t]*["'"'"']?[A-Za-z_][A-Za-z0-9_]*["'"'"']?/)) {
          d=substr(line, RSTART, RLENGTH)
          gsub(/^<<-?[ \t]*["'"'"']?/, "", d)
          gsub(/["'"'"']?$/, "", d)
          hd=d
        }
        print line
        next
      }

      # --- In the target section, before its bash block opens ---
      # Check this FIRST so the section bash opener is not swallowed by the
      # top-level fence tracker below.
      if (in_section) {
        if (line ~ /^```bash$/) { in_block=1; next }
        if (line ~ /^## /) { exit }   # next real section header — give up
        next
      }

      # --- Top-level scanning for the section header ---
      # Track top-level fenced code blocks so that headers/fences embedded inside
      # an earlier section bash block (e.g. heredoc fixtures) never trip section
      # detection. While inside a top-level fence, ignore all ## headers.
      if (top_fence) {
        if (line ~ /^```$/) top_fence=0
        next
      }
      if (line ~ /^```/) { top_fence=1; next }

      if (lower == "## " want) { in_section=1 }
    }
  ' "$FILE"
}

sc_bash=$(extract_bash_block "success criteria")
ec_bash=$(extract_bash_block "exit check")

if [[ -z "$sc_bash" ]]; then
  if [[ "$CI_MODE" == true ]]; then
    echo '{"eval":"_runner","status":"fail","message":"no bash block found in Success Criteria"}'
  else
    echo "FAIL: no bash block found in Success Criteria" >&2
  fi
  exit 1
fi

if [[ -z "$ec_bash" ]]; then
  if [[ "$CI_MODE" == true ]]; then
    echo '{"eval":"_runner","status":"fail","message":"no bash block found in Exit Check"}'
  else
    echo "FAIL: no bash block found in Exit Check" >&2
  fi
  exit 1
fi

# Find all eval_N() functions defined in Success Criteria
defined_evals=$(echo "$sc_bash" | grep -oE 'eval_[0-9]+\(\)' | sed 's/()//' | sort -u || true)

# Find evals called in Exit Check
called_evals=$(echo "$ec_bash" | grep -oE 'eval_[0-9]+' | sort -u || true)

# Warn about uncalled evals
for ev in $defined_evals; do
  if ! echo "$called_evals" | grep -qx "$ev"; then
    if [[ "$CI_MODE" == true ]]; then
      printf '{"eval":"%s","status":"warn","message":"defined in Success Criteria but not called in Exit Check"}\n' "$ev"
    else
      echo "WARN: $ev is defined but not called in Exit Check" >&2
    fi
  fi
done

# Create temp directory
tmp_dir=$(mktemp -d)
trap 'rm -rf "$tmp_dir"' EXIT

# Write eval definitions script
eval_script="$tmp_dir/evals.sh"
{
  echo '#!/usr/bin/env bash'
  echo 'set -euo pipefail'
  printf 'GIT_ROOT="%s"\n' "$GIT_ROOT"
  printf 'WORKSPACE_ROOT="%s"\n' "$EVAL_CWD"
  echo 'export GIT_ROOT WORKSPACE_ROOT'
  printf 'cd "%s" || exit 1\n' "$EVAL_CWD"
  echo "$sc_bash"
} > "$eval_script"

# JSON escape helper
json_escape() {
  if command -v python3 >/dev/null 2>&1; then
    python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()), end="")'
  else
    local str
    str=$(cat)
    str="${str//\\/\\\\}"
    str="${str//\"/\\\"}"
    str="${str//
/\\n}"
    str="${str//
/}"
    str="${str//	/\\t}"
    printf '"%s"' "$str"
  fi
}

# Run each eval individually and report. The final verdict is the Exit Check's
# exit code (below), per the signed_off contract — per-eval results are
# informational, so no aggregate pass flag is accumulated here.
for eval_name in $defined_evals; do
  out_file="$tmp_dir/${eval_name}.out"
  err_file="$tmp_dir/${eval_name}.err"

  start_time=$(date +%s)

  # stdin is redirected from /dev/null so an eval that reads stdin (or a
  # malformed body whose unbalanced quote/backtick makes bash wait for more
  # input) gets EOF immediately instead of HANGING on the caller's terminal or
  # pipe. A gate must never block waiting for input it will never receive.
  if bash -c "source '$eval_script'; $eval_name" > "$out_file" 2> "$err_file" < /dev/null; then
    status="pass"
  else
    status="fail"
  fi

  end_time=$(date +%s)
  duration=$((end_time - start_time))

  stdout_content=$(cat "$out_file" 2>/dev/null || true)
  stderr_content=$(cat "$err_file" 2>/dev/null || true)

  if [[ "$CI_MODE" == true ]]; then
    stdout_json=$(printf '%s' "$stdout_content" | json_escape)
    stderr_json=$(printf '%s' "$stderr_content" | json_escape)
    printf '{"eval":"%s","status":"%s","duration_sec":%d,"stdout":%s,"stderr":%s}\n' \
      "$eval_name" "$status" "$duration" "$stdout_json" "$stderr_json"
  else
    printf '[%s] %s (%ss)\n' "$status" "$eval_name" "$duration"
    if [[ -n "$stdout_content" ]]; then
      printf '%s\n' "$stdout_content" | sed 's/^/  /'
    fi
    if [[ -n "$stderr_content" ]]; then
      printf '%s\n' "$stderr_content" | sed 's/^/  [stderr] /'
    fi
  fi
done

# Run Exit Check for final verdict
ec_script="$tmp_dir/exit_check.sh"
{
  echo '#!/usr/bin/env bash'
  echo 'set -euo pipefail'
  printf 'GIT_ROOT="%s"\n' "$GIT_ROOT"
  printf 'WORKSPACE_ROOT="%s"\n' "$EVAL_CWD"
  echo 'export GIT_ROOT WORKSPACE_ROOT'
  printf 'cd "%s" || exit 1\n' "$EVAL_CWD"
  echo "$sc_bash"
  echo "$ec_bash"
} > "$ec_script"

ec_out="$tmp_dir/ec.out"
ec_err="$tmp_dir/ec.err"

ec_start=$(date +%s)
if bash "$ec_script" > "$ec_out" 2> "$ec_err" < /dev/null; then
  ec_status="pass"
  ec_code=0
else
  ec_status="fail"
  ec_code=1
fi
ec_end=$(date +%s)
ec_duration=$((ec_end - ec_start))

ec_stdout=$(cat "$ec_out" 2>/dev/null || true)
ec_stderr=$(cat "$ec_err" 2>/dev/null || true)

if [[ "$CI_MODE" == true ]]; then
  stdout_json=$(printf '%s' "$ec_stdout" | json_escape)
  stderr_json=$(printf '%s' "$ec_stderr" | json_escape)
  printf '{"eval":"_exit_check","status":"%s","duration_sec":%d,"stdout":%s,"stderr":%s}\n' \
    "$ec_status" "$ec_duration" "$stdout_json" "$stderr_json"
else
  printf 'Exit Check: %s (%ss)\n' "$ec_status" "$ec_duration"
  if [[ -n "$ec_stdout" ]]; then
    printf '%s\n' "$ec_stdout" | sed 's/^/  /'
  fi
  if [[ -n "$ec_stderr" ]]; then
    printf '%s\n' "$ec_stderr" | sed 's/^/  [stderr] /'
  fi
fi

exit "$ec_code"
