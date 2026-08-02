#!/usr/bin/env bash
# safe-to-delegate.sh — single pre-delegation gate for a Task-Spec.
#
# Composes the existing validator + runner into one go/no-go verdict so the
# eval-discipline ritual is one command, not three. Run this before handing a
# spec to Kimi/Codex/any executor blind.
#
# It answers: "are this spec's evals well-formed enough to delegate safely?"
#   - structurally valid (validate-task-spec.sh)
#   - eval bodies are shellcheck-clean (no syntax / unquoted-var bugs)
#   - eval bodies EXECUTE without bash errors (broken-logic guard)
#   - the evals can tell real work from a STUB (existence-only evals block
#     blind delegation; --supervised downgrades that to a note)
#
# For a not-yet-built task the evals are EXPECTED to fail (the work isn't done).
# That is fine — a delegate-safe spec fails for the RIGHT reason (assertion not
# yet true) rather than the WRONG reason (the eval itself is broken bash).
#
# Usage:
#   bash safe-to-delegate.sh <path/to/T-*.md>
#   bash safe-to-delegate.sh --skip-touches-paths <path>   # greenfield create tasks
#   bash safe-to-delegate.sh --require-tier1 <path>         # demand crypto trust
#   bash safe-to-delegate.sh --supervised <path>            # a human reads the diff
#
# Machine-readable contract (for automated dispatchers):
#   On a clean DELEGATE verdict for a signed-off spec, the gate emits exactly
#   one line of the form `TIER=N` (N = 1|2|3) to stdout. A dispatcher SHOULD
#   parse that line rather than the colored prose:
#     TIER=1  crypto trust (HMAC verified)        -> unsupervised dispatch OK
#     TIER=2  structural-only (no key / no sig)   -> SUPERVISED dispatch ONLY
#     TIER=3  HMAC mismatch                        -> never reached here (hard FAIL)
#   An unsigned spec (no `signed_off: true`) emits no TIER line.
#   With --require-tier1, anything below Tier 1 makes the gate exit 1 — turning
#   the "supervised-only" policy into an enforced control for CI pipelines.
#
# Exit codes:
#   0 — DELEGATE: spec is safe to hand off (Tier 1, or Tier 2 without --require-tier1)
#   1 — DO NOT DELEGATE: structural error, broken eval, shellcheck failure, or
#       (with --require-tier1) a sign-off below Tier 1
#   2 — usage / file error

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Source shared lib (TASKSPEC_VERSION, ts_version_flag, ts_die)
# shellcheck source=./_lib.sh
source "$SCRIPT_DIR/_lib.sh"

# Handle --version uniformly across all task-spec scripts
ts_version_flag "$@"

VALIDATE="$SCRIPT_DIR/validate-task-spec.sh"
RUNNER="$SCRIPT_DIR/run-task-spec.sh"

PASS_THROUGH=()
FILE=""
STAMP=false
STAMP_BY="${USER:-operator}"
REQUIRE_TIER1=false
# A human will read the diff. Relaxes only the checks whose whole purpose is to
# substitute for a reviewer — never the structural or crypto gates.
SUPERVISED=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-touches-paths|--skip-id-filename|--skip-depends-on|--skip-exit-coverage)
      PASS_THROUGH+=("$1"); shift ;;
    --stamp)
      STAMP=true; shift ;;
    --stamp-by)
      STAMP=true; STAMP_BY="${2:-operator}"; shift 2 ;;
    --require-tier1)
      REQUIRE_TIER1=true; shift ;;
    --supervised)
      SUPERVISED=true; shift ;;
    --help|-h)
      grep '^#' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*)
      echo "Unknown option: $1" >&2; exit 2 ;;
    *)
      if [[ -z "$FILE" ]]; then FILE="$1"; else echo "Too many arguments" >&2; exit 2; fi
      shift ;;
  esac
done

if [[ -z "$FILE" ]]; then
  echo "Usage: safe-to-delegate.sh [--skip-touches-paths] <path/to/T-*.md>" >&2
  exit 2
fi
if [[ ! -f "$FILE" ]]; then
  echo "FAIL: file not found: $FILE" >&2
  exit 2
fi

BOLD=$'\033[1m'; GREEN=$'\033[32m'; RED=$'\033[31m'; YELLOW=$'\033[33m'; RESET=$'\033[0m'
# Disable color when not a TTY
if [[ ! -t 1 ]]; then BOLD=""; GREEN=""; RED=""; YELLOW=""; RESET=""; fi

blockers=0
notes=()

echo "${BOLD}safe-to-delegate: $FILE${RESET}"
echo "────────────────────────────────────────────────────────"

# --- Re-sealing: retire the superseded signature BEFORE validation ---
# A signed spec must be amendable. Every doc says the remedy for an edited spec
# is "re-run safe-to-delegate.sh --stamp to re-seal", and that remedy was
# UNREACHABLE: the validator raises the HMAC mismatch as a blocker in Gate 1,
# and the --stamp branch only runs when blockers == 0. So the one legitimate way
# to amend a sealed spec dead-ended in the error telling you to use it, and the
# only way through was to hand-strip the sig — exactly what the docs forbid.
#
# `--stamp` IS the act of signing off: it declares that the body as it stands
# now is the thing being signed. So the previous signature is superseded by
# definition and is retired here, before anything reads it. This grants no
# authority — the fresh MAC still requires the signing key, and without one the
# spec lands at Tier 2 (supervised only) just as it would on a first stamp.
if [[ "$STAMP" == true ]] && grep -q '^signed_off_sig:' "$FILE"; then
  _ss_tmp="$(mktemp -t cvg-reseal.XXXXXX)"
  if grep -v '^signed_off_sig:' "$FILE" > "$_ss_tmp" && mv "$_ss_tmp" "$FILE"; then
    echo "   ${YELLOW}re-sealing${RESET} — the previous signature is superseded by this stamp"
  else
    rm -f "$_ss_tmp"
    echo "   ${RED}BLOCK${RESET} — could not retire the previous signature; spec NOT stamped." >&2
    exit 1
  fi
fi

# --- Gate 0: leaf-only — a NODE (XL/XXL) is NEVER delegated ---
# The dark-factory invariant: a worker runs LEAVES. An XL/XXL node is a
# decomposition directive; delegating it would run the node instead of its
# children. Block early and point at the slices. (effort-gate.md)
STD_EFFORT=$(grep -m1 '^effort:' "$FILE" | awk '{print $2}' || true)
if ts_size_is_valid "$STD_EFFORT" && ! ts_size_is_leaf "$STD_EFFORT"; then
  echo "0. Delegatability (leaf-only) ..."
  echo "   ${RED}BLOCK${RESET} — '$STD_EFFORT' is a decomposition NODE, not a runnable unit."
  echo "     A worker must dispatch its child task-specs (the leaves in 'children:'), never the node itself."
  echo "     See references/concepts/effort-gate.md."
  echo "${BOLD}${RED}VERDICT: DO NOT DELEGATE${RESET} — node, not a leaf; dispatch its children."
  exit 1
fi

# --- Gate 1: structural + shellcheck validation ---
echo "1. Structural validation + shellcheck-evals ..."
set +e
# "${ARR[@]+"${ARR[@]}"}" — not the bare "${ARR[@]}".
#
# Under `set -u`, bash 3.2 treats expanding an EMPTY array as an unbound variable
# and dies. bash 4.4+ fixed it, so with no pass-through flags this gate ran fine
# on Linux and aborted on stock macOS — reporting "blocked a valid spec", which
# reads like a spec defect and is really the gate failing to start. This repo
# declares bash 3.2 as its floor, and the same idiom is already used in the Pass 8
# engine adapters for exactly this reason.
# A gate is a read-only verdict unless --stamp was explicitly requested.
# Validation's derived-index refresh is useful when invoked directly, but would
# make a plain sign-off check mutate _state.yaml and contradict the gate/JSON
# contract. The task's status is unchanged here, so suppress that side effect.
v_out=$(bash "$VALIDATE" --no-state --shellcheck-evals ${PASS_THROUGH[@]+"${PASS_THROUGH[@]}"} "$FILE" 2>&1)
v_rc=$?
set -e
if [[ $v_rc -ne 0 ]]; then
  echo "   ${RED}BLOCK${RESET} — validator reported errors:"
  echo "$v_out" | grep -E '^\s+-' | sed 's/^/     /' | head -10
  blockers=$((blockers + 1))
else
  if echo "$v_out" | grep -q '^WARN:'; then
    echo "   ${YELLOW}PASS (with warnings)${RESET}"
    notes+=("validator warnings present — review but not blocking")
  else
    echo "   ${GREEN}PASS${RESET} — structurally valid, shellcheck clean"
  fi
fi

# --- Gate 1b: existence-only evals are disqualifying for BLIND delegation ---
# The validator warns; this gate blocks. That split is the whole architecture:
# `validate` lints a spec, `safe-to-delegate` decides whether a machine may run
# it with nobody watching. A spec whose every check is "the file exists" cannot
# distinguish real work from a stub, so an unsupervised loop would settle green
# on three empty files. Supervised work may proceed — a human sees the diff.
if echo "$v_out" | grep -q 'existence-only evals'; then
  if [[ "$SUPERVISED" == true ]]; then
    echo "   ${YELLOW}NOTE${RESET} — existence-only evals, allowed because --supervised (a human reads the diff)"
    notes+=("existence-only evals — a stub would satisfy this spec; supervision is doing the real verification")
  else
    echo "   ${RED}BLOCK${RESET} — existence-only evals: a stub file satisfies every check."
    echo "     Make at least one eval EXECUTE what the task produces, or pass --supervised,"
    echo "     or annotate the spec with '# task-spec:allow-existence-only' if it really is a document."
    blockers=$((blockers + 1))
  fi
fi

# --- Gate 2: evals execute without bash errors (broken-logic guard) ---
# We run the evals; failures are EXPECTED (work not built). We only block when an
# eval produces a bash-level error (syntax, unbound var, command-not-found),
# which means the eval itself is broken — not the assertion.
echo "2. Eval execution (broken-logic guard) ..."
# The entire analysis runs under set +e: every grep/wc here legitimately returns
# non-zero when it finds nothing, which must NOT abort the gate (CLAUDE.md gotcha).
set +e
r_out=$(bash "$RUNNER" --ci "$FILE" 2>&1)

# Detect bash-level breakage in stderr of any eval: these indicate a BROKEN eval,
# distinct from a clean assertion-fail (which is expected for unbuilt work).
broken=$(printf '%s\n' "$r_out" | grep -oE '"stderr":"[^"]*"' \
  | grep -iE 'syntax error|unbound variable|command not found|unexpected (end|token)|: line [0-9]+:' \
  | head -3)
runner_error=$(printf '%s\n' "$r_out" | grep -oE '"eval":"_runner"[^}]*"status":"fail"[^}]*' | head -1)
passes=$(printf '%s\n' "$r_out" | grep -oE '"status":"pass"' | wc -l | tr -d ' ')
fails=$(printf '%s\n' "$r_out" | grep -oE '"status":"fail"' | wc -l | tr -d ' ')
set -e

if [[ -n "$runner_error" ]]; then
  echo "   ${RED}BLOCK${RESET} — runner could not parse/execute the spec:"
  echo "     $runner_error"
  blockers=$((blockers + 1))
elif [[ -n "$broken" ]]; then
  echo "   ${RED}BLOCK${RESET} — eval body has a bash-level error (broken eval, not a clean fail):"
  echo "$broken" | sed 's/^/     /'
  blockers=$((blockers + 1))
else
  echo "   ${GREEN}PASS${RESET} — evals execute cleanly (${passes:-0} pass / ${fails:-0} fail; fails are expected for unbuilt work)"
  if [[ "${passes:-0}" -gt 0 && "${fails:-0}" -eq 0 ]]; then
    notes+=("ALL evals already pass — task may already be DONE; verify before delegating")
  fi
fi

# --- Verdict ---
echo "────────────────────────────────────────────────────────"
if [[ ${#notes[@]} -gt 0 ]]; then
  for n in "${notes[@]}"; do echo "   ${YELLOW}note:${RESET} $n"; done
fi
if [[ $blockers -eq 0 ]]; then
  echo "${BOLD}${GREEN}VERDICT: DELEGATE${RESET} — safe to hand off blind."
  # TIER is the machine-readable sign-off trust level: 0 = unsigned (no
  # signed_off:true), 1 = crypto trust, 2 = structural-only, 3 = MAC mismatch.
  # It is computed against the spec's ACTUAL on-disk state after any --stamp,
  # then surfaced as a single `TIER=N` line and (with --require-tier1) enforced.
  TIER=0
  # --stamp: the gate writes the autonomy contract into the task frontmatter.
  # This is the Sign-Off Line made real — past this, the task runs unattended.
  if [[ "$STAMP" == true ]]; then
    ts="$(date -u +%FT%TZ)"
    # Write the three envelope fields. CRITICAL: signed_off_by carries a
    # user/CI-controlled value (--stamp-by, $USER). It MUST NOT flow through a
    # sed substitution (a `|` closes the delimiter, an `&` expands to the match)
    # NOR through `awk -v` (which C-escape-expands a backslash-n into a real
    # newline, injecting a forged frontmatter line). ts_set_frontmatter_field is
    # the one serialization path: it carries the value verbatim via the process
    # environment (ENVIRON[]), so every byte — `|`, `&`, `\`, backslash-n, tab —
    # is written literally. The same primitive later writes signed_off_sig.
    if ! ts_set_frontmatter_field "$FILE" "signed_off"    "true" \
       || ! ts_set_frontmatter_field "$FILE" "signed_off_by" "$STAMP_BY" \
       || ! ts_set_frontmatter_field "$FILE" "signed_off_at" "$ts"; then
      echo "   ${RED}BLOCK${RESET} — could not write sign-off envelope (bad --stamp-by value or malformed frontmatter); spec NOT stamped." >&2
      exit 1
    fi
    echo "   ${GREEN}stamped${RESET} signed_off: true by ${STAMP_BY} at ${ts}"

    # --- B2: key-optional HMAC envelope (v2.2) ---
    # The 3 plaintext signed_off* lines are now final on disk. Compute the MAC
    # over the CANONICAL payload (ts_signoff_payload reads those 3 values + the
    # body digest + id, and EXCLUDES the signed_off_sig line itself, so the MAC
    # verifies on the very next read regardless of frontmatter line ordering).
    #
    # Key-optional: with no key (fresh clone / no env var) OR no crypto binary,
    # we DO NOT write a sig and we DO NOT fail — the spec is a structural-only
    # (Tier 2) sign-off, dispatch-eligible for supervised use only. Crypto trust
    # (Tier 1) requires a key + a sha256 provider.
    sig=""
    key="$(ts_resolve_signing_key "$FILE" 2>/dev/null || true)"
    if [[ -n "$key" ]]; then
      set +e
      sig="$(ts_compute_signoff_sig "$FILE" "$key")"
      sig_rc=$?
      set -e
      if [[ $sig_rc -eq 0 && -n "$sig" ]]; then
        # Write the sig via the SAME rewrite-or-inject primitive as the
        # plaintext fields (single serialization path; no sed delimiter).
        if ! ts_set_frontmatter_field "$FILE" "signed_off_sig" "$sig"; then
          echo "   ${RED}BLOCK${RESET} — could not write signed_off_sig into frontmatter; spec stamped but UNSEALED." >&2
          exit 1
        fi
        # Report the envelope version that was ACTUALLY written. Hardcoding v1
        # here outlived the v2 envelope and told every operator their spec was
        # sealed v1 while the file said v2 — the one line whose whole job is to
        # state what just happened.
        sig_ver="${sig%%:*}"                      # hmac-sha256-v2
        keyid_disp="${sig#"$sig_ver":}"; keyid_disp="${keyid_disp%%:*}"
        echo "   ${GREEN}sealed${RESET}  signed_off_sig: ${sig_ver} (keyid ${keyid_disp}) — Tier 1 crypto trust"
      else
        echo "   ${YELLOW}note:${RESET} key present but no sha256 provider (openssl/shasum/sha256sum) — structural-only (Tier 2), supervised dispatch only"
      fi
    else
      echo "   ${YELLOW}note:${RESET} no signing key resolved — structural-only (Tier 2), supervised dispatch only. Run configs/setup-taskspec-signing-key.sh or set TASKSPEC_SIGNING_KEY for Tier 1 crypto trust."
    fi
  fi

  # --- Sign-off TIER (computed against actual on-disk state, post-stamp) ---
  # An unsigned spec keeps TIER=0 (no envelope to evaluate). A signed spec is
  # Tier 1 (key+sig present and MAC verifies), Tier 3 (MAC mismatch — should
  # never reach a clean DELEGATE since validate Check 17 hard-fails it), or
  # Tier 2 (structural-only: no key or no sig).
  so_now=$(grep -m1 '^signed_off:' "$FILE" 2>/dev/null | awk -F: '{print $2}' | xargs || true)
  if [[ "${so_now:-}" == "true" ]]; then
    sig_now=$(grep -m1 '^signed_off_sig:' "$FILE" 2>/dev/null | sed -E 's/^signed_off_sig:[[:space:]]*//' || true)
    key_now="$(ts_resolve_signing_key "$FILE" 2>/dev/null || true)"
    if [[ -n "$key_now" && -n "$sig_now" ]]; then
      set +e
      expected_sig="$(ts_compute_signoff_sig "$FILE" "$key_now")"
      set -e
      if [[ -n "$expected_sig" && "$expected_sig" == "$sig_now" ]]; then
        TIER=1
        echo "   ${GREEN}sign-off: Tier 1${RESET} — HMAC verified, full crypto trust (unsupervised dispatch OK)"
      elif [[ "$sig_now" == hmac-sha256-v1:* ]]; then
        # A v1 seal is AUTHENTIC-BUT-NARROW: it proves the prose is untouched, but
        # it never covered write scope, dependencies, budgets, or routing. Those
        # could have changed since stamping, so it cannot authorize unsupervised
        # work. Verify it on its own terms and downgrade rather than cry forgery.
        set +e
        legacy_sig="$(ts_compute_signoff_sig "$FILE" "$key_now" v1)"
        set -e
        if [[ -n "$legacy_sig" && "$legacy_sig" == "$sig_now" ]]; then
          TIER=2
          echo "   ${YELLOW}sign-off: legacy envelope v1 (Tier 2)${RESET} — authentic, but the seal predates authorization sealing"
          echo "   ${YELLOW}         ${RESET}  write scope, dependencies, budgets and routing were NOT covered."
          echo "   ${YELLOW}         ${RESET}  Re-stamp to regain Tier 1: safe-to-delegate.sh --stamp ${FILE}"
        else
          TIER=3
          echo "   ${RED}sign-off: Tier 3${RESET} — HMAC MISMATCH; spec body or envelope modified after stamping (DO NOT DELEGATE unsupervised)"
        fi
      else
        TIER=3
        echo "   ${RED}sign-off: Tier 3${RESET} — HMAC MISMATCH; spec body, authorization fields, or envelope modified after stamping (DO NOT DELEGATE unsupervised)"
      fi
    else
      TIER=2
      echo "   ${YELLOW}sign-off: structural-only (Tier 2)${RESET} — supervised dispatch only (no key or no signed_off_sig)"
    fi
  fi

  # Machine-readable tier line for automated dispatchers (parse this, not prose).
  # Emitted only for a signed spec; an unsigned spec has no envelope to report.
  if [[ "${so_now:-}" == "true" ]]; then
    echo "TIER=${TIER}"
  fi

  # --require-tier1: turn the "supervised-only" policy into an ENFORCED control.
  # Anything below Tier 1 (unsigned, structural-only, or a slipped-through
  # mismatch) is a hard FAIL so a CI dispatcher cannot crank it unsupervised.
  if [[ "$REQUIRE_TIER1" == true && "$TIER" != "1" ]]; then
    echo "${BOLD}${RED}VERDICT: DO NOT DELEGATE${RESET} — --require-tier1 set but sign-off is Tier ${TIER} (need Tier 1 crypto trust)." >&2
    exit 1
  fi
  exit 0
else
  echo "${BOLD}${RED}VERDICT: DO NOT DELEGATE${RESET} — $blockers blocker(s) above. Fix the spec first."
  exit 1
fi
