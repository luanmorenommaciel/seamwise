#!/usr/bin/env bash
# setup-taskspec-signing-key.sh — provision the repo's Task-Spec signing key (B2).
#
# The signing key is the shared secret behind the HMAC sign-off envelope
# (signed_off_sig: hmac-sha256-v1:<keyid>:<hex>). With a key present, the gate
# (safe-to-delegate.sh --stamp) SEALS each sign-off and the verifier
# (validate-task-spec.sh Check 17) recomputes the MAC to reach Tier 1 (full
# crypto trust). Without a key, sign-off degrades to Tier 2 (structural-only,
# supervised dispatch only). See references/concepts/signed-off.md.
#
# This script:
#   1. Generates a 256-bit key (openssl rand -hex 32, or /dev/urandom + xxd).
#   2. Writes it to a path you choose (default: <git-dir>/info/taskspec-signing-key,
#      where <git-dir> is whatever `git rev-parse --git-dir` resolves to — `.git`
#      in a normal clone, or the per-worktree gitdir in a linked worktree, both
#      of which work). Only when NO real git dir is resolvable (non-git tree,
#      some bare CI checkouts) does it print instructions to export
#      TASKSPEC_SIGNING_KEY instead.
#   3. chmod 600 the key file so it is owner-readable only.
#   4. Prints the keyid (first 8 hex of sha256 of the key) so you can recognise
#      which key a given stamp was sealed under.
#
# The key is a SECRET. It is stored OUTSIDE version control:
#   - .git/info/ is never committed (it is part of the local .git directory).
#   - If you instead export TASKSPEC_SIGNING_KEY, keep it in a gitignored file
#     or your shell profile / secret manager — never commit it.
#
# Threat model (honest): HMAC is SYMMETRIC. Anyone who can read this key can
# forge a Tier-1 stamp. The key binds "a repo-key holder stamped this", NOT
# "person X specifically". Per-author non-repudiation (Ed25519/DSSE) is a future
# upgrade. The adversary this defends against is a co-author who read the skill
# and hand-edits an envelope — not a remote attacker who already has your key.
#
# Usage:
#   bash configs/setup-taskspec-signing-key.sh                 # default location
#   bash configs/setup-taskspec-signing-key.sh --path PATH     # explicit file
#   bash configs/setup-taskspec-signing-key.sh --print-only    # print key+keyid, write nothing
#   bash configs/setup-taskspec-signing-key.sh --force         # overwrite an existing key
#   bash configs/setup-taskspec-signing-key.sh --version
#
# Exit codes:
#   0  key provisioned (or printed)
#   1  refused to overwrite an existing key without --force
#   2  usage / environment error

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# _lib.sh lives in ../scripts relative to configs/.
# shellcheck source=../scripts/_lib.sh
source "$SCRIPT_DIR/../scripts/_lib.sh"

ts_version_flag "$@"

KEY_PATH=""
PRINT_ONLY=false
FORCE=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --path)        KEY_PATH="${2:-}"; shift 2 ;;
    --print-only)  PRINT_ONLY=true; shift ;;
    --force)       FORCE=true; shift ;;
    --help|-h)     grep '^#' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*)            echo "Unknown option: $1" >&2; exit 2 ;;
    *)             echo "Unexpected argument: $1" >&2; exit 2 ;;
  esac
done

# ----- Generate 256-bit key material (hex) -----
gen_key() {
  if command -v openssl >/dev/null 2>&1 && openssl rand -hex 32 >/dev/null 2>&1; then
    openssl rand -hex 32
  elif command -v xxd >/dev/null 2>&1; then
    head -c 32 /dev/urandom | xxd -p | tr -d '\n'
  elif command -v od >/dev/null 2>&1; then
    head -c 32 /dev/urandom | od -An -v -tx1 | tr -d ' \n'
  else
    echo "ERROR: no key generator available (need openssl, xxd, or od)" >&2
    exit 2
  fi
}

KEY="$(gen_key)"
if [[ ${#KEY} -ne 64 ]]; then
  echo "ERROR: generated key is not 64 hex chars (got ${#KEY}); aborting" >&2
  exit 2
fi
KEYID="$(ts_keyid "$KEY")"

# ----- Resolve default key path when not given -----
# Default to <git-dir>/info/taskspec-signing-key. <git-dir> is whatever
# `git rev-parse --git-dir` resolves to: `.git` in a normal clone, or the
# per-worktree gitdir (…/.git/worktrees/<name>) in a linked worktree — so a
# worktree IS supported, the key just lives in its own gitdir. A relative
# gitdir is canonicalized to absolute. Only when no real git dir is resolvable
# (non-git tree, some bare CI checkouts) do we fall back to printing
# TASKSPEC_SIGNING_KEY instructions.
GIT_DIR=""
if command -v git >/dev/null 2>&1; then
  GIT_DIR="$(git rev-parse --git-dir 2>/dev/null || true)"
  if [[ -n "$GIT_DIR" && "$GIT_DIR" != /* ]]; then
    GIT_DIR="$(cd "$GIT_DIR" 2>/dev/null && pwd || true)"
  fi
fi

if [[ -z "$KEY_PATH" && ! "$PRINT_ONLY" == true ]]; then
  if [[ -n "$GIT_DIR" && -d "$GIT_DIR" ]]; then
    mkdir -p "$GIT_DIR/info"
    KEY_PATH="$GIT_DIR/info/taskspec-signing-key"
  fi
fi

# ----- Print-only mode: emit and stop -----
if [[ "$PRINT_ONLY" == true ]]; then
  echo "key:   $KEY"
  echo "keyid: $KEYID"
  echo ""
  echo "To use without writing a file, export it in your shell (keep it secret):"
  echo "  export TASKSPEC_SIGNING_KEY=$KEY"
  exit 0
fi

# ----- No resolvable git dir and no --path: print env-var instructions -----
if [[ -z "$KEY_PATH" ]]; then
  echo "No git directory resolved from here (this looks like a non-git tree, or a"
  echo "checkout where 'git rev-parse --git-dir' yields no real directory)."
  echo "Use an environment variable instead:"
  echo ""
  echo "  export TASKSPEC_SIGNING_KEY=$KEY"
  echo ""
  echo "Put that line in a gitignored file (e.g. configs/.envrc) or your secret"
  echo "manager — NEVER commit it. keyid: $KEYID"
  echo ""
  echo "Or choose an explicit path: bash $(basename "${BASH_SOURCE[0]}") --path /secure/location/key"
  exit 0
fi

# ----- Refuse to clobber an existing key unless --force -----
if [[ -e "$KEY_PATH" && "$FORCE" != true ]]; then
  EXISTING_KEYID="$(ts_keyid "$(cat "$KEY_PATH")" 2>/dev/null || echo unknown)"
  echo "Refusing to overwrite existing key at: $KEY_PATH (keyid: $EXISTING_KEYID)" >&2
  echo "Re-run with --force to rotate the key. WARNING: rotating invalidates every" >&2
  echo "existing signed_off_sig — those specs will drop from Tier 1 to Tier 3 on" >&2
  echo "verify and must be re-stamped." >&2
  exit 1
fi

# ----- Write the key (atomic, chmod 600) -----
umask 077
TMP="${KEY_PATH}.tmp.$$"
printf '%s\n' "$KEY" > "$TMP"
chmod 600 "$TMP"
mv "$TMP" "$KEY_PATH"
chmod 600 "$KEY_PATH"

echo "Signing key written: $KEY_PATH (chmod 600)"
echo "keyid: $KEYID"
echo ""
echo "This file is OUTSIDE version control (.git/info is never committed)."
echo "Stamps produced by 'cvg tasks gate --stamp' will now reach Tier 1"
echo "(full crypto trust). Verify with: cvg tasks validate <spec>"
exit 0
