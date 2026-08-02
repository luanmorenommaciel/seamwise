#!/usr/bin/env bash
# accept-task.sh — POST-execution acceptance gate for a Task-Spec (C7).
#
# Position in the lifecycle:
#   AUTHOR → safe-to-delegate.sh (PRE-gate) → DISPATCH → EXECUTE → accept-task.sh (POST-gate)
#
# safe-to-delegate asks "are this spec's evals well-formed enough to delegate?"
# (assertion failure is EXPECTED — the work is not built yet). accept-task asks
# the OPPOSITE question: "now that an executor claims it is done, is the work
# REAL?" — and it answers WITHOUT trusting the executor's word, by checking three
# independent trust gaps:
#
#   GATE A — evals PASS (re-run by us). The Exit Check must return 0. This is the
#            inversion of safe-to-delegate: there, a pass on unbuilt work is a
#            smell; here, a pass is the whole point.
#   GATE B — blast-radius compliance. Every changed file must be inside
#            touches_paths/creates_paths and NONE in do-not-touch. Defends against
#            an agent that satisfied the eval by editing things it should not have
#            (the Goodhart guard). Skipped with --no-blast-radius for ad-hoc use.
#   GATE C — contract integrity. The sign-off HMAC envelope must still verify, i.e.
#            the eval bodies / behavior were NOT edited after the gate stamped them.
#            Defends against an agent that made evals pass by weakening them.
#            Degrades to a warning (not a block) when no key/crypto is present,
#            mirroring the Tier-2 degrade of the sign-off envelope.
#
# On success it stamps the acceptance envelope into the frontmatter:
#   accepted: true, accepted_by: <user>, accepted_at: <iso-8601>
# A spec is DONE — provably, not by assertion — only when accept-task returns
# VERDICT: ACCEPT and writes that envelope.
#
# Two OPT-IN B3 gates harden against 2026-era reward-hacking (a "clean re-run" is
# not enough — e.g. an eval that passes by retrieval or that is simply always-true):
#
#   GATE D — isolation report (requires:). If the spec declares a `requires:` block
#            (base_image / deps / network), REPORT what isolation the executor's
#            sandbox must have provided. The bash tool cannot enforce egress, so
#            this is DOCUMENT-AND-WARN, never a blocker — EXCEPT it WARNS (still not
#            a block) when a `full`-profile spec leaves requires.network UNSET, since
#            an unattended full task with undeclared egress is the reward-hacking
#            attack surface. Absent `requires:` on a non-full profile → silent.
#   GATE E — gold-sanity (--gold-sanity, opt-in). The Goodhart-guard upgrade: an eval
#            that PASSES on the UNPATCHED baseline is non-discriminating (always-true /
#            reward-hackable) and is BLOCKED. It reconstructs the baseline in an
#            ephemeral git worktree at the baseline ref (--base, or a frontmatter
#            baseline_ref:/reference_solution:), runs the CURRENT spec's evals there
#            (must FAIL), and runs them on the current state (must PASS). Degrades to
#            a WARN (never a hard-fail) when git or the baseline ref is unavailable.
#
# Usage:
#   bash accept-task.sh [--stamp] [--no-blast-radius] [--gold-sanity] \
#                       [--accepted-by NAME] [--base REF] <path/to/T-*.md>
#
# Flags:
#   --stamp            write the accepted envelope on success (default: dry-run report only)
#   --no-blast-radius  skip GATE B (changed-files-vs-touches_paths). Use when the
#                      change set is intentionally broad or git is unavailable.
#   --gold-sanity      enable GATE E (gold-sanity). OFF by default so existing
#                      callers are unchanged. BLOCKS any eval that passes on the
#                      unpatched baseline (non-discriminating / reward-hackable).
#   --accepted-by NAME override the accepted_by value (default: $USER)
#   --base REF         git ref to diff the change set against for GATE B, and the
#                      baseline ref for GATE E gold-sanity (default: HEAD).
#                      A frontmatter baseline_ref:/reference_solution: overrides the
#                      default for GATE E only.
#
# Machine-readable contract:
#   On ACCEPT, emits exactly one line `ACCEPTED=1` to stdout (dispatchers parse it).
#   On REJECT, emits `ACCEPTED=0` and exits 1.
#
# Exit codes:
#   0 — ACCEPT: the work is real (evals pass + blast-radius clean + envelope intact)
#   1 — REJECT: a gate failed; the spec is NOT accepted
#   2 — usage / file error

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./_lib.sh
source "$SCRIPT_DIR/_lib.sh"

ts_version_flag "$@"

RUNNER="$SCRIPT_DIR/run-task-spec.sh"

FILE=""
STAMP=false
CHECK_BLAST=true
GOLD_SANITY=false
ACCEPTED_BY="${USER:-operator}"
BASE_REF="HEAD"
BASE_EXPLICIT=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --stamp)            STAMP=true; shift ;;
    --no-blast-radius)  CHECK_BLAST=false; shift ;;
    --gold-sanity)      GOLD_SANITY=true; shift ;;
    --accepted-by)      ACCEPTED_BY="${2:-operator}"; shift 2 ;;
    --base)             BASE_REF="${2:-HEAD}"; BASE_EXPLICIT=true; shift 2 ;;
    --help|-h)          grep '^#' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*)                 echo "Unknown option: $1" >&2; exit 2 ;;
    *)
      if [[ -z "$FILE" ]]; then FILE="$1"; else echo "Too many arguments" >&2; exit 2; fi
      shift ;;
  esac
done

if [[ -z "$FILE" ]]; then
  echo "Usage: accept-task.sh [--stamp] [--no-blast-radius] [--accepted-by NAME] <path/to/T-*.md>" >&2
  exit 2
fi
if [[ ! -f "$FILE" ]]; then
  echo "REJECT: file not found: $FILE" >&2
  exit 2
fi

BOLD=$'\033[1m'; GREEN=$'\033[32m'; RED=$'\033[31m'; YELLOW=$'\033[33m'; RESET=$'\033[0m'
if [[ ! -t 1 ]]; then BOLD=""; GREEN=""; RED=""; YELLOW=""; RESET=""; fi

GIT_ROOT=$(cd "$(dirname "$FILE")" && git rev-parse --show-toplevel 2>/dev/null || echo "")
blockers=0
notes=()

echo "${BOLD}accept-task: $FILE${RESET}"
echo "────────────────────────────────────────────────────────"

# Precondition: the spec must have been signed off. Acceptance presupposes the
# gate — you cannot accept work that was never delegate-safe.
SO=$(grep -m1 '^signed_off:' "$FILE" 2>/dev/null | awk -F: '{print $2}' | xargs || true)
if [[ "${SO:-false}" != "true" ]]; then
  echo "   ${RED}BLOCK${RESET} — spec is not signed_off:true. Run safe-to-delegate.sh --stamp first (gate → dispatch → accept)."
  blockers=$((blockers + 1))
fi

# --- GATE A: evals PASS (re-run by us, not trusted from the executor) ---
echo "A. Evals pass (Exit Check returns 0) ..."
set +e
a_out=$(bash "$RUNNER" "$FILE" 2>&1)
a_rc=$?
set -e
if [[ $a_rc -eq 0 ]]; then
  echo "   ${GREEN}PASS${RESET} — Exit Check returned 0; the work satisfies its own success criteria"
else
  echo "   ${RED}BLOCK${RESET} — Exit Check did NOT pass (rc=$a_rc). The work is not done:"
  printf '%s\n' "$a_out" | grep -E '^\[fail\]|Exit Check:' | sed 's/^/     /' | head -8
  blockers=$((blockers + 1))
fi

# --- GATE B: blast-radius compliance (changed files ⊆ touches/creates, ∩ do-not-touch = ∅) ---
if [[ "$CHECK_BLAST" == true ]]; then
  echo "B. Blast-radius (changed files vs touches_paths / do-not-touch) ..."
  if [[ -z "$GIT_ROOT" ]]; then
    echo "   ${YELLOW}skip${RESET} — not in a git repo; cannot compute the change set"
    notes+=("blast-radius unchecked (no git)")
  else
    FRONTMATTER=$(ts_frontmatter "$FILE")
    # Allowed = touches_paths ∪ creates_paths. Forbidden = do-not-touch entries.
    allowed=$( { echo "$FRONTMATTER" | sed -n '/^touches_paths:/,/^[^ -]/p' | grep -E '^[[:space:]]*-' ; \
                 echo "$FRONTMATTER" | sed -n '/^creates_paths:/,/^[^ -]/p' | grep -E '^[[:space:]]*-' ; } \
               | sed -E 's/^[[:space:]]*-[[:space:]]*//' | sed -E 's/[[:space:]]*$//' | grep -v '^$' | sort -u || true)
    forbidden=$(awk '/^## Do-Not-Touch/{f=1; next} /^## /{f=0} f' "$FILE" 2>/dev/null \
                | grep -oE '`[^`]+`' | tr -d '`' | sort -u || true)
    # The change set: tracked modifications + staged + untracked, vs BASE_REF.
    set +e
    changed=$( { cd "$GIT_ROOT" && git diff --name-only "$BASE_REF" 2>/dev/null; \
                 cd "$GIT_ROOT" && git diff --name-only --cached 2>/dev/null; \
                 cd "$GIT_ROOT" && git ls-files --others --exclude-standard 2>/dev/null; } \
               | sort -u | grep -v '^$' || true)
    set -e

    # The task file itself and the backlog ledger are always allowed to change.
    # Compute the spec's path RELATIVE to the repo via git, not by string-stripping
    # GIT_ROOT — on macOS `git rev-parse --show-toplevel` resolves /tmp → /private/tmp
    # so a literal prefix strip can fail. `git -C <dir> ls-files --full-name` (or a
    # realpath-based relativization) yields the canonical repo-relative path.
    spec_dir="$(cd "$(dirname "$FILE")" && pwd)"
    spec_base="$(basename "$FILE")"
    self_rel="$(cd "$spec_dir" && git ls-files --full-name -- "$spec_base" 2>/dev/null | head -1 || true)"
    if [[ -z "$self_rel" ]]; then
      # Untracked (newly authored) spec: derive repo-relative path from the toplevel.
      _top="$(cd "$spec_dir" && git rev-parse --show-toplevel 2>/dev/null || echo "$GIT_ROOT")"
      self_rel="${spec_dir#"$_top"/}/$spec_base"
    fi
    out_of_scope=()
    touched_forbidden=()
    while IFS= read -r f; do
      [[ -z "$f" ]] && continue
      # Exempt the spec file itself (by repo-relative path OR basename — the task
      # file is unambiguous and is expected to change as the executor stamps it).
      [[ "$f" == "$self_rel" ]] && continue
      [[ "$(basename "$f")" == "$spec_base" ]] && continue
      # FRAMEWORK OUTPUT is not the task's work.
      #
      # These patterns were anchored at the repo root (`tasks/_state.yaml`), but in
      # the cvg/ layout the real path is nested — `<project>/cvg/tasks/_state.yaml`
      # — so they never matched. And the loop's own outputs were not listed at
      # all. So `cvg tasks accept` REJECTED a task whose work was demonstrably
      # done, naming the ledger row, the receipt and the index that Pass 8 is
      # REQUIRED to write as a "blast-radius breach".
      #
      # check-path-policy.py already exempts exactly this set at settlement. Having
      # a second gate invent its own answer is the same root cause as the workspace
      # derivations above; until one resolver owns it, the two lists must agree.
      case "$f" in
        */tasks/_state.yaml|tasks/_state.yaml) continue ;;
        */tasks/_metrics.jsonl|tasks/_metrics.jsonl) continue ;;
        */cvg/STATE.md|cvg/STATE.md) continue ;;
        */cvg/receipts/*|cvg/receipts/*) continue ;;
        */cvg/loop/*|cvg/loop/*) continue ;;
        */cvg/execution/_packs/*|cvg/execution/_packs/*) continue ;;
        .gitignore) continue ;;
      esac
      # Skip tooling exhaust + gitignored paths: a build artifact (e.g. a Python
      # __pycache__/*.pyc produced merely by RUNNING the eval) or any gitignored
      # file is not "work" and must not count as a blast-radius breach. git
      # check-ignore is authoritative (respects nested .gitignore + excludes).
      case "$f" in
        */__pycache__/*|__pycache__/*|*.pyc|*.pyo|.pytest_cache/*|*/.pytest_cache/*) continue ;;
      esac
      if ( cd "$GIT_ROOT" && git check-ignore -q -- "$f" ) 2>/dev/null; then
        continue
      fi
      # The spec's own backlog dir entries (tasks/) are author-side bookkeeping.
      case "$f" in
        "$TASKSPEC_BACKLOG_DIR"/T-*.md) continue ;;
        tasks/T-*.md|*/tasks/T-*.md) continue ;;
      esac
      # Forbidden check (prefix match against do-not-touch entries).
      while IFS= read -r df; do
        [[ -z "$df" ]] && continue
        if [[ "$f" == "$df" || "$f" == "$df"/* ]]; then touched_forbidden+=("$f (do-not-touch: $df)"); fi
      done <<< "$forbidden"
      # Allowed check: f must match some allowed entry (exact or dir-prefix).
      ok=false
      while IFS= read -r af; do
        [[ -z "$af" ]] && continue
        if [[ "$f" == "$af" || "$f" == "$af"/* ]]; then ok=true; break; fi
      done <<< "$allowed"
      if [[ "$ok" != true ]]; then out_of_scope+=("$f"); fi
    done <<< "$changed"

    if [[ ${#touched_forbidden[@]} -gt 0 ]]; then
      echo "   ${RED}BLOCK${RESET} — modified a do-not-touch path:"
      printf '     %s\n' "${touched_forbidden[@]}" | head -8
      blockers=$((blockers + 1))
    elif [[ ${#out_of_scope[@]} -gt 0 ]]; then
      echo "   ${RED}BLOCK${RESET} — changed files OUTSIDE touches_paths/creates_paths (blast-radius breach):"
      printf '     %s\n' "${out_of_scope[@]}" | head -8
      echo "     (declare these under touches_paths/creates_paths if intended, or revert them)"
      blockers=$((blockers + 1))
    else
      echo "   ${GREEN}PASS${RESET} — every changed file is within the declared blast radius"
    fi
  fi
else
  echo "B. Blast-radius — ${YELLOW}skipped${RESET} (--no-blast-radius)"
  notes+=("blast-radius check skipped by flag")
fi

# --- GATE C: contract integrity (sign-off HMAC still verifies) ---
echo "C. Contract integrity (eval bodies / envelope unchanged since sign-off) ..."
SIGNED_SIG=$(grep -m1 '^signed_off_sig:' "$FILE" 2>/dev/null | sed -E 's/^signed_off_sig:[[:space:]]*//' || true)
set +e
SIGN_KEY="$(ts_resolve_signing_key "$FILE" 2>/dev/null)"
set -e
if [[ -z "$SIGN_KEY" || -z "$SIGNED_SIG" ]]; then
  echo "   ${YELLOW}note${RESET} — no key or no signed_off_sig; integrity is structural-only (Tier 2). Set TASKSPEC_SIGNING_KEY for full crypto trust."
  notes+=("contract integrity unverified (Tier 2)")
else
  set +e
  EXPECTED_SIG="$(ts_compute_signoff_sig "$FILE" "$SIGN_KEY")"
  esig_rc=$?
  set -e
  if [[ $esig_rc -ne 0 || -z "$EXPECTED_SIG" ]]; then
    echo "   ${YELLOW}note${RESET} — key present but no sha256 provider to verify; structural-only (Tier 2)."
    notes+=("contract integrity unverified (no crypto)")
  elif [[ "$EXPECTED_SIG" == "$SIGNED_SIG" ]]; then
    echo "   ${GREEN}PASS${RESET} — sign-off HMAC verifies; eval bodies and behavior were NOT edited after the gate"
  else
    echo "   ${RED}BLOCK${RESET} — sign-off HMAC MISMATCH: the spec body changed after sign-off. An executor may have weakened the evals. DO NOT ACCEPT."
    blockers=$((blockers + 1))
  fi
fi

# --- GATE D: isolation report (requires:) — document-and-warn, never a blocker ---
# The bash tool cannot enforce network egress; this gate REPORTS the isolation the
# executor's sandbox must provide so a dispatcher (or a human reviewer) can confirm
# it was honored. It only WARNS (does not block) when a full-profile spec leaves
# requires.network unset — an unattended full task with undeclared egress is exactly
# the surface 2026 reward-hacking exploits. Specs with no requires: on a non-full
# profile stay silent (zero behavior change for the historical/default case).
PROFILE="$(ts_profile "$FILE")"
if ts_has_requires "$FILE"; then
  echo "D. Isolation requirements (requires:) — the executor sandbox MUST have provided:"
  req_base="$(ts_requires_field "$FILE" base_image)"
  req_deps="$(ts_requires_field "$FILE" deps)"
  req_net="$(ts_requires_field "$FILE" network)"
  [[ -n "$req_base" ]] && echo "   - base_image: $req_base"
  [[ -n "$req_deps" ]] && echo "   - deps:       $req_deps"
  if [[ -n "$req_net" ]]; then
    echo "   - network:    $req_net (egress posture the sandbox enforces, not this gate)"
  else
    echo "   ${YELLOW}note${RESET} — requires.network is unset; the executor's egress posture is undeclared"
    notes+=("requires.network undeclared")
  fi
  if [[ "$PROFILE" == "full" && -z "$req_net" ]]; then
    echo "   ${YELLOW}WARN${RESET} — full-profile spec with no requires.network: an unattended task should pin egress (deny|allow-list|open) to close the reward-hacking surface"
    notes+=("full profile missing requires.network (warn, not block)")
  fi
elif [[ "$PROFILE" == "full" ]]; then
  echo "D. Isolation requirements — ${YELLOW}WARN${RESET}: full-profile spec declares no requires: block (base_image/deps/network). Add one so the sandbox isolation is auditable. (warn, not block)"
  notes+=("full profile has no requires: block (warn, not block)")
fi

# --- GATE E: gold-sanity (opt-in) — the Goodhart-guard upgrade ---
# An eval that passes EVEN on the unpatched baseline is non-discriminating: it
# proves nothing about the work and is exactly what a reward-hacking executor would
# satisfy. We reconstruct the baseline in an EPHEMERAL git worktree at the baseline
# ref, drop the CURRENT spec into it (so eval BODIES are held constant — only the
# implementation reverts), and require the evals to FAIL there while PASSING on the
# current state. Degrades to a warn (never a hard-fail) when git/baseline is absent.
if [[ "$GOLD_SANITY" == true ]]; then
  echo "E. Gold-sanity (evals must FAIL on the unpatched baseline) ..."
  if [[ -z "$GIT_ROOT" ]]; then
    echo "   ${YELLOW}skip${RESET} — not in a git repo; cannot reconstruct the baseline"
    notes+=("gold-sanity unchecked (no git)")
  else
    GS_OVERRIDE=""
    [[ "$BASE_EXPLICIT" == true ]] && GS_OVERRIDE="$BASE_REF"
    GS_REF="$(ts_baseline_ref "$FILE" "$GS_OVERRIDE")"
    [[ -z "$GS_REF" ]] && GS_REF="$BASE_REF"
    FILE_ABS="$(cd "$(dirname "$FILE")" && pwd)/$(basename "$FILE")"
    set +e
    bash "$RUNNER" "$FILE_ABS" >/dev/null 2>&1
    gs_cur_rc=$?
    set -e
    gs_wt="$(mktemp -d)"
    set +e
    ( cd "$GIT_ROOT" && git worktree add -q --detach "$gs_wt" "$GS_REF" ) >/dev/null 2>&1
    gs_wt_rc=$?
    set -e
    if [[ $gs_wt_rc -ne 0 ]]; then
      rm -rf "$gs_wt"
      echo "   ${YELLOW}skip${RESET} — could not check out baseline ref '$GS_REF' (unknown ref / shallow clone); gold-sanity not run"
      notes+=("gold-sanity unchecked (baseline ref '$GS_REF' unavailable)")
    else
      gs_rel="$(cd "$GIT_ROOT" && git ls-files --full-name -- "$FILE_ABS" 2>/dev/null | head -1 || true)"
      [[ -z "$gs_rel" ]] && gs_rel="${TASKSPEC_BACKLOG_DIR}/$(basename "$FILE_ABS")"
      mkdir -p "$gs_wt/$(dirname "$gs_rel")"
      cp "$FILE_ABS" "$gs_wt/$gs_rel"
      set +e
      bash "$RUNNER" "$gs_wt/$gs_rel" >/dev/null 2>&1
      gs_base_rc=$?
      set -e
      ( cd "$GIT_ROOT" && git worktree remove --force "$gs_wt" ) >/dev/null 2>&1 || rm -rf "$gs_wt"
      if [[ $gs_cur_rc -ne 0 ]]; then
        echo "   ${RED}BLOCK${RESET} — evals do NOT pass on the current state (rc=$gs_cur_rc); gold-sanity cannot certify discrimination"
        blockers=$((blockers + 1))
      elif [[ $gs_base_rc -eq 0 ]]; then
        echo "   ${RED}BLOCK${RESET} — NON-DISCRIMINATING eval set: the Exit Check PASSES on the unpatched baseline ('$GS_REF'). An always-true / reward-hackable eval proves nothing — strengthen it so it FAILS without the work. DO NOT ACCEPT."
        blockers=$((blockers + 1))
      else
        echo "   ${GREEN}PASS${RESET} — discriminating: evals FAIL on baseline '$GS_REF' and PASS on the current state"
      fi
    fi
  fi
fi

# --- Verdict ---
echo "────────────────────────────────────────────────────────"
for n in "${notes[@]:-}"; do [[ -n "$n" ]] && echo "   ${YELLOW}note:${RESET} $n"; done

if [[ $blockers -ne 0 ]]; then
  echo "${BOLD}${RED}VERDICT: REJECT${RESET} — $blockers gate(s) failed. The work is not provably done."
  echo "ACCEPTED=0"
  exit 1
fi

echo "${BOLD}${GREEN}VERDICT: ACCEPT${RESET} — evals pass, blast radius clean, contract intact. The work is real."

if [[ "$STAMP" == true ]]; then
  ts="$(date -u +%FT%TZ)"
  if ! ts_set_frontmatter_field "$FILE" "accepted"    "true" \
     || ! ts_set_frontmatter_field "$FILE" "accepted_by" "$ACCEPTED_BY" \
     || ! ts_set_frontmatter_field "$FILE" "accepted_at" "$ts"; then
    echo "   ${RED}BLOCK${RESET} — could not write acceptance envelope; spec NOT stamped." >&2
    exit 1
  fi
  echo "   ${GREEN}stamped${RESET} accepted: true by ${ACCEPTED_BY} at ${ts}"
  mkdir -p "$TASKSPEC_BACKLOG_DIR"
  ts_append_metric "$TASKSPEC_BACKLOG_DIR/_metrics.jsonl" \
    schema_version 1 ts "$ts" task "$(basename "$FILE" .md)" \
    event accepted author "$ACCEPTED_BY"
fi

echo "ACCEPTED=1"
exit 0
