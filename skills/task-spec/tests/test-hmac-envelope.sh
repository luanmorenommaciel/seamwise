#!/usr/bin/env bash
# test-hmac-envelope.sh — keyed B2 HMAC sign-off envelope suite (v2.2).
#
# The default oracle (tests/test-task-spec-skill.sh --suite fixtures) runs with
# NO key, so it can only exercise Tier 2. This suite owns the KEYED paths:
#   Tier 1 — stamp a fresh spec under an ephemeral key, verify immediately.
#   Tier 3 — tamper the BODY (then an envelope VALUE), verify hard-fails.
#   Tier 3 — verify under a DIFFERENT key, and a MALFORMED sig, hard-fail.
#   Tier 2 — no key at all, and key-present-but-crypto-masked, degrade (exit 0).
#   Portability floor — PATH-mask openssl+shasum+sha256sum; stamp+verify never
#                       hard-error, they degrade to Tier 2.
#   Key location — .git/info/taskspec-signing-key fallback resolves with no env.
#
# Each scenario sets up and tears down its own isolated git tempdir. Safe to run
# anytime; never touches the real backlog.
#
# Usage:
#   bash tests/test-hmac-envelope.sh
#   bash tests/test-hmac-envelope.sh --version

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../scripts/_lib.sh
source "$SKILL_DIR/scripts/_lib.sh"
ts_version_flag "$@"

FIXTURES="$SKILL_DIR/tests/fixtures"
SAFE="$SKILL_DIR/scripts/safe-to-delegate.sh"
VALIDATE="$SKILL_DIR/scripts/validate-task-spec.sh"
SETUP_KEY="$SKILL_DIR/configs/setup-taskspec-signing-key.sh"

PASS=0
FAIL=0
pass() { echo "  ✓ $1"; PASS=$((PASS + 1)); }
fail() { echo "  ✗ $1" >&2; FAIL=$((FAIL + 1)); }

# Create an isolated git repo with a README and the named fixture copied into
# tasks/<id>.md. Echoes the repo dir. Caller must rm -rf it.
make_repo() {
  local fixture="$1" id="$2" repo
  repo=$(mktemp -d -t ts-hmac-XXXXXX)
  (
    cd "$repo"
    git init --quiet
    git config user.email "test@hmac.local"
    git config user.name "hmac test"
    echo "# readme" > README.md
    mkdir -p tasks
    cp "$FIXTURES/$fixture" "tasks/$id.md"
  )
  echo "$repo"
}

# Make an executable stub-dir that masks the three sha256 providers (exit 127),
# prepended to the real PATH. Echoes the masked PATH string.
masked_path() {
  local shim
  shim=$(mktemp -d -t ts-mask-XXXXXX)
  local t
  for t in openssl shasum sha256sum; do
    printf '#!/bin/sh\nexit 127\n' > "$shim/$t"
    chmod +x "$shim/$t"
  done
  echo "$shim:$PATH"
}

echo "═══ test-hmac-envelope.sh (B2 keyed suite, v2.2) ═══"

# ---------------------------------------------------------------------------
# Scenario 1 — Tier 1: stamp then verify (payload boundary self-consistency)
# ---------------------------------------------------------------------------
echo "── Scenario 1: Tier 1 stamp-then-verify ──"
{
  ID="T-20260603-stamp-then-verify"
  REPO=$(make_repo "$ID.md" "$ID")
  KEYFILE=$(mktemp); head -c 32 /dev/urandom | xxd -p | tr -d '\n' > "$KEYFILE"
  (
    cd "$REPO"
    export TASKSPEC_SIGNING_KEY="$KEYFILE"
    stamp_out=$(bash "$SAFE" --stamp --stamp-by hmac-test "tasks/$ID.md" 2>&1) || true
    if echo "$stamp_out" | grep -q "sealed"; then
      echo "PASS sealed"
    else
      echo "FAIL stamp did not seal: $stamp_out"
    fi
    if grep -qE '^signed_off_sig: hmac-sha256-v2:[0-9a-zA-Z]+:[0-9a-f]+$' "tasks/$ID.md"; then
      echo "PASS sig-format"
    else
      echo "FAIL sig field malformed or absent"
    fi
    set +e
    v_out=$(bash "$VALIDATE" "tasks/$ID.md" 2>&1); v_rc=$?
    set -e
    if [[ $v_rc -eq 0 ]] && echo "$v_out" | grep -q "Tier 1"; then
      echo "PASS verify-tier1"
    else
      echo "FAIL verify did not reach Tier 1 (rc=$v_rc): $(echo "$v_out" | tail -2)"
    fi
  ) > "$REPO/out.txt" 2>&1
  while IFS= read -r line; do
    case "$line" in
      PASS\ *) pass "S1 ${line#PASS }" ;;
      FAIL\ *) fail "S1 ${line#FAIL }" ;;
    esac
  done < "$REPO/out.txt"
  rm -rf "$REPO" "$KEYFILE"
}

# ---------------------------------------------------------------------------
# Scenario 2 — Tier 3: tamper the BODY after stamping
# ---------------------------------------------------------------------------
echo "── Scenario 2: Tier 3 tampered body ──"
{
  ID="T-20260603-tampered-body"
  REPO=$(make_repo "$ID.md" "$ID")
  KEYFILE=$(mktemp); head -c 32 /dev/urandom | xxd -p | tr -d '\n' > "$KEYFILE"
  (
    cd "$REPO"
    export TASKSPEC_SIGNING_KEY="$KEYFILE"
    bash "$SAFE" --stamp --stamp-by hmac-test "tasks/$ID.md" >/dev/null 2>&1 || true
    # Verify Tier 1 BEFORE tampering (sanity)
    set +e
    pre_out=$(bash "$VALIDATE" "tasks/$ID.md" 2>&1); pre_rc=$?
    set -e
    if [[ $pre_rc -eq 0 ]] && echo "$pre_out" | grep -q "Tier 1"; then
      echo "PASS pre-tamper-tier1"
    else
      echo "FAIL pre-tamper not Tier 1 (rc=$pre_rc)"
    fi
    # Tamper ONE token in the BODY
    sed 's/original-marker-do-not-edit/tampered-marker-edited-here/' "tasks/$ID.md" > t && mv t "tasks/$ID.md"
    set +e
    post_out=$(bash "$VALIDATE" "tasks/$ID.md" 2>&1); post_rc=$?
    set -e
    if [[ $post_rc -ne 0 ]] && echo "$post_out" | grep -q "DO NOT DELEGATE: spec body"; then
      echo "PASS tamper-caught-tier3"
    else
      echo "FAIL tamper not caught (rc=$post_rc): $(echo "$post_out" | tail -2)"
    fi
  ) > "$REPO/out.txt" 2>&1
  while IFS= read -r line; do
    case "$line" in
      PASS\ *) pass "S2 ${line#PASS }" ;;
      FAIL\ *) fail "S2 ${line#FAIL }" ;;
    esac
  done < "$REPO/out.txt"
  rm -rf "$REPO" "$KEYFILE"
}

# ---------------------------------------------------------------------------
# Scenario 3 — Tier 3: tamper an envelope VALUE, wrong key, malformed sig
# ---------------------------------------------------------------------------
echo "── Scenario 3: Tier 3 envelope tamper / wrong key / malformed ──"
{
  ID="T-20260603-stamp-then-verify"
  REPO=$(make_repo "$ID.md" "$ID")
  KEYFILE=$(mktemp); head -c 32 /dev/urandom | xxd -p | tr -d '\n' > "$KEYFILE"
  (
    cd "$REPO"
    export TASKSPEC_SIGNING_KEY="$KEYFILE"

    # 3a: tamper signed_off_by after stamping
    cp "$FIXTURES/$ID.md" "tasks/$ID.md"
    bash "$SAFE" --stamp "tasks/$ID.md" >/dev/null 2>&1 || true
    sed 's/^signed_off_by:.*/signed_off_by: attacker/' "tasks/$ID.md" > t && mv t "tasks/$ID.md"
    set +e; o=$(bash "$VALIDATE" "tasks/$ID.md" 2>&1); rc=$?; set -e
    if [[ $rc -ne 0 ]] && echo "$o" | grep -q "modified after stamping"; then
      echo "PASS envelope-value-tamper"
    else
      echo "FAIL envelope-value-tamper (rc=$rc)"
    fi

    # 3b: verify under a DIFFERENT key
    cp "$FIXTURES/$ID.md" "tasks/$ID.md"
    bash "$SAFE" --stamp "tasks/$ID.md" >/dev/null 2>&1 || true
    head -c 32 /dev/urandom | xxd -p | tr -d '\n' > "$KEYFILE"   # rotate key
    set +e; o=$(bash "$VALIDATE" "tasks/$ID.md" 2>&1); rc=$?; set -e
    if [[ $rc -ne 0 ]] && echo "$o" | grep -q "HMAC mismatch"; then
      echo "PASS wrong-key-tier3"
    else
      echo "FAIL wrong-key-tier3 (rc=$rc)"
    fi

    # 3c: malformed sig field
    head -c 32 /dev/urandom | xxd -p | tr -d '\n' > "$KEYFILE"
    cp "$FIXTURES/$ID.md" "tasks/$ID.md"
    bash "$SAFE" --stamp "tasks/$ID.md" >/dev/null 2>&1 || true
    sed 's/^signed_off_sig:.*/signed_off_sig: not-a-valid-envelope/' "tasks/$ID.md" > t && mv t "tasks/$ID.md"
    set +e; o=$(bash "$VALIDATE" "tasks/$ID.md" 2>&1); rc=$?; set -e
    if [[ $rc -ne 0 ]] && echo "$o" | grep -q "signed_off_sig is malformed"; then
      echo "PASS malformed-sig-tier3"
    else
      echo "FAIL malformed-sig-tier3 (rc=$rc)"
    fi
  ) > "$REPO/out.txt" 2>&1
  while IFS= read -r line; do
    case "$line" in
      PASS\ *) pass "S3 ${line#PASS }" ;;
      FAIL\ *) fail "S3 ${line#FAIL }" ;;
    esac
  done < "$REPO/out.txt"
  rm -rf "$REPO" "$KEYFILE"
}

# ---------------------------------------------------------------------------
# Scenario 4 — Tier 2: no key, and stamped-then-no-key, degrade (exit 0)
# ---------------------------------------------------------------------------
echo "── Scenario 4: Tier 2 no-key degrade ──"
{
  ID="T-20260603-stamp-then-verify"
  REPO=$(make_repo "$ID.md" "$ID")
  KEYFILE=$(mktemp); head -c 32 /dev/urandom | xxd -p | tr -d '\n' > "$KEYFILE"
  (
    cd "$REPO"
    # 4a: stamp with key, then verify with NO key -> Tier 2 (structural-only), exit 0
    TASKSPEC_SIGNING_KEY="$KEYFILE" bash "$SAFE" --stamp "tasks/$ID.md" >/dev/null 2>&1 || true
    set +e
    o=$(env -u TASKSPEC_SIGNING_KEY bash "$VALIDATE" "tasks/$ID.md" 2>&1); rc=$?
    set -e
    if [[ $rc -eq 0 ]] && echo "$o" | grep -qi "Tier 2"; then
      echo "PASS no-key-tier2"
    else
      echo "FAIL no-key did not degrade to Tier 2 (rc=$rc): $(echo "$o" | tail -2)"
    fi
    # 4b: a legacy spec (signed_off:true, no sig line) with a key present -> Tier 2
    cp "$FIXTURES/T-20260603-fake-envelope.md" "tasks/legacy.md"
    set +e
    o=$(TASKSPEC_SIGNING_KEY="$KEYFILE" bash "$VALIDATE" --skip-id-filename --skip-touches-paths "tasks/legacy.md" 2>&1); rc=$?
    set -e
    if [[ $rc -eq 0 ]] && echo "$o" | grep -qi "Tier 2"; then
      echo "PASS legacy-nosig-tier2"
    else
      echo "FAIL legacy-nosig not Tier 2 (rc=$rc): $(echo "$o" | tail -2)"
    fi
  ) > "$REPO/out.txt" 2>&1
  while IFS= read -r line; do
    case "$line" in
      PASS\ *) pass "S4 ${line#PASS }" ;;
      FAIL\ *) fail "S4 ${line#FAIL }" ;;
    esac
  done < "$REPO/out.txt"
  rm -rf "$REPO" "$KEYFILE"
}

# ---------------------------------------------------------------------------
# Scenario 5 — Portability floor: mask all three sha256 providers
# ---------------------------------------------------------------------------
echo "── Scenario 5: portability floor (crypto masked) ──"
{
  ID="T-20260603-stamp-then-verify"
  REPO=$(make_repo "$ID.md" "$ID")
  KEYFILE=$(mktemp); head -c 32 /dev/urandom | xxd -p | tr -d '\n' > "$KEYFILE"
  MASKED=$(masked_path)
  SHIMDIR="${MASKED%%:*}"
  (
    cd "$REPO"
    export TASKSPEC_SIGNING_KEY="$KEYFILE"
    # provider must report none under masked PATH
    prov=$(PATH="$MASKED" bash -c "source '$SKILL_DIR/scripts/_lib.sh'; ts_sha256_provider")
    if [[ "$prov" == "none" ]]; then echo "PASS provider-none"; else echo "FAIL provider=$prov (expected none)"; fi
    # stamp under masked PATH -> DELEGATE, no sig, exit 0
    set +e
    s=$(PATH="$MASKED" bash "$SAFE" --stamp "tasks/$ID.md" 2>&1); src=$?
    set -e
    if echo "$s" | grep -q "VERDICT: DELEGATE" && ! grep -q '^signed_off_sig:' "tasks/$ID.md"; then
      echo "PASS masked-stamp-no-sig"
    else
      echo "FAIL masked stamp wrote sig or did not DELEGATE (rc=$src)"
    fi
    # seal WITH real crypto, then verify under masked PATH -> Tier 2, exit 0, no hard error
    cp "$FIXTURES/$ID.md" "tasks/$ID.md"
    bash "$SAFE" --stamp "tasks/$ID.md" >/dev/null 2>&1 || true
    set +e
    v=$(PATH="$MASKED" bash "$VALIDATE" "tasks/$ID.md" 2>&1); vrc=$?
    set -e
    if [[ $vrc -eq 0 ]] && echo "$v" | grep -qi "Tier 2"; then
      echo "PASS masked-verify-tier2"
    else
      echo "FAIL masked verify hard-errored or not Tier 2 (rc=$vrc): $(echo "$v" | tail -2)"
    fi
  ) > "$REPO/out.txt" 2>&1
  while IFS= read -r line; do
    case "$line" in
      PASS\ *) pass "S5 ${line#PASS }" ;;
      FAIL\ *) fail "S5 ${line#FAIL }" ;;
    esac
  done < "$REPO/out.txt"
  rm -rf "$REPO" "$KEYFILE" "$SHIMDIR"
}

# ---------------------------------------------------------------------------
# Scenario 6 — Key location: .git/info fallback (no env var)
# ---------------------------------------------------------------------------
echo "── Scenario 6: .git/info key fallback ──"
{
  ID="T-20260603-stamp-then-verify"
  REPO=$(make_repo "$ID.md" "$ID")
  (
    cd "$REPO"
    bash "$SETUP_KEY" >/dev/null 2>&1
    if [[ -f ".git/info/taskspec-signing-key" ]]; then echo "PASS keyfile-written"; else echo "FAIL keyfile not written"; fi
    # stamp + verify with NO env var; key must resolve from .git/info
    set +e
    s=$(env -u TASKSPEC_SIGNING_KEY bash "$SAFE" --stamp "tasks/$ID.md" 2>&1); src=$?
    set -e
    if echo "$s" | grep -q "sealed"; then echo "PASS gitinfo-stamp-sealed"; else echo "FAIL gitinfo stamp did not seal"; fi
    set +e
    v=$(env -u TASKSPEC_SIGNING_KEY bash "$VALIDATE" "tasks/$ID.md" 2>&1); vrc=$?
    set -e
    if [[ $vrc -eq 0 ]] && echo "$v" | grep -q "Tier 1"; then echo "PASS gitinfo-verify-tier1"; else echo "FAIL gitinfo verify not Tier 1 (rc=$vrc)"; fi
  ) > "$REPO/out.txt" 2>&1
  while IFS= read -r line; do
    case "$line" in
      PASS\ *) pass "S6 ${line#PASS }" ;;
      FAIL\ *) fail "S6 ${line#FAIL }" ;;
    esac
  done < "$REPO/out.txt"
  rm -rf "$REPO"
}

# ---------------------------------------------------------------------------
# Scenario 7 — Injection-safe --stamp-by (regression for the v2.2 sed-injection
# finding). A user/CI identity containing sed metacharacters MUST be written
# verbatim, seal to a VALID Tier 1, and never silently mis-seal or mis-attribute.
# Inputs are the exact adversarial-review breakers: `build|42` (was: silent
# non-sign), `a&b` (was: wrong attribution with a valid seal), and a full
# injection payload (was: whole-file rewrite).
# ---------------------------------------------------------------------------
echo "── Scenario 7: injection-safe --stamp-by ──"
{
  ID="T-20260603-stamp-then-verify"
  REPO=$(make_repo "$ID.md" "$ID")
  KEYFILE=$(mktemp); head -c 32 /dev/urandom | xxd -p | tr -d '\n' > "$KEYFILE"
  (
    cd "$REPO"
    export TASKSPEC_SIGNING_KEY="$KEYFILE"
    for who in 'build|42' 'a&b' 'team/build' 'X|p;s|.*|INJECTED' 'name with space'; do
      cp "$FIXTURES/$ID.md" "tasks/$ID.md"
      set +e
      s=$(bash "$SAFE" --stamp --stamp-by "$who" "tasks/$ID.md" 2>&1); src=$?
      set -e
      disk_by=$(grep -m1 '^signed_off_by:' "tasks/$ID.md" | sed -E 's/^signed_off_by:[[:space:]]*//')
      sigcount=$(grep -c '^signed_off_sig:' "tasks/$ID.md")
      set +e
      v=$(bash "$VALIDATE" "tasks/$ID.md" 2>&1); vrc=$?
      set -e
      if [[ "$disk_by" == "$who" && "$sigcount" == "1" && $vrc -eq 0 ]] \
         && echo "$s" | grep -q "Tier 1 crypto trust" \
         && echo "$v" | grep -q "Tier 1"; then
        echo "PASS literal-verbatim-tier1 [$who]"
      else
        echo "FAIL [$who] disk_by=[$disk_by] sigcount=$sigcount vrc=$vrc"
      fi
    done
  ) > "$REPO/out.txt" 2>&1
  while IFS= read -r line; do
    case "$line" in
      PASS\ *) pass "S7 ${line#PASS }" ;;
      FAIL\ *) fail "S7 ${line#FAIL }" ;;
    esac
  done < "$REPO/out.txt"
  rm -rf "$REPO" "$KEYFILE"
}

# ---------------------------------------------------------------------------
# Scenario 8 — Tier enforcement: --require-tier1 + machine-readable TIER line.
# The gate MUST emit `TIER=N` for a signed spec, and --require-tier1 MUST turn
# the "supervised-only" Tier-2 policy into a hard non-zero exit (an enforced
# control, not prose). Tier 1 passes the flag; Tier 2 fails it; without the
# flag Tier 2 still delegates (exit 0).
# ---------------------------------------------------------------------------
echo "── Scenario 8: --require-tier1 enforcement + TIER= line ──"
{
  ID="T-20260603-stamp-then-verify"
  REPO=$(make_repo "$ID.md" "$ID")
  KEYFILE=$(mktemp); head -c 32 /dev/urandom | xxd -p | tr -d '\n' > "$KEYFILE"
  (
    cd "$REPO"
    # 8a: Tier 1 + --require-tier1 -> exit 0, TIER=1 emitted
    cp "$FIXTURES/$ID.md" "tasks/$ID.md"
    set +e
    o=$(TASKSPEC_SIGNING_KEY="$KEYFILE" bash "$SAFE" --stamp --require-tier1 "tasks/$ID.md" 2>&1); rc=$?
    set -e
    if [[ $rc -eq 0 ]] && echo "$o" | grep -q '^TIER=1$'; then
      echo "PASS tier1-require-passes"
    else
      echo "FAIL tier1-require-passes (rc=$rc) tierline=[$(echo "$o" | grep '^TIER=')]"
    fi
    # 8b: Tier 2 (no key) + --require-tier1 -> exit 1, TIER=2 still emitted
    cp "$FIXTURES/$ID.md" "tasks/$ID.md"
    set +e
    o=$(env -u TASKSPEC_SIGNING_KEY bash "$SAFE" --stamp --require-tier1 "tasks/$ID.md" 2>&1); rc=$?
    set -e
    if [[ $rc -ne 0 ]] && echo "$o" | grep -q '^TIER=2$' && echo "$o" | grep -q "require-tier1"; then
      echo "PASS tier2-require-blocks"
    else
      echo "FAIL tier2-require-blocks (rc=$rc): $(echo "$o" | grep -E 'TIER=|require')"
    fi
    # 8c: Tier 2 (no key) WITHOUT the flag -> exit 0 (supervised dispatch allowed)
    cp "$FIXTURES/$ID.md" "tasks/$ID.md"
    set +e
    o=$(env -u TASKSPEC_SIGNING_KEY bash "$SAFE" --stamp "tasks/$ID.md" 2>&1); rc=$?
    set -e
    if [[ $rc -eq 0 ]] && echo "$o" | grep -q '^TIER=2$'; then
      echo "PASS tier2-noflag-delegates"
    else
      echo "FAIL tier2-noflag-delegates (rc=$rc)"
    fi
  ) > "$REPO/out.txt" 2>&1
  while IFS= read -r line; do
    case "$line" in
      PASS\ *) pass "S8 ${line#PASS }" ;;
      FAIL\ *) fail "S8 ${line#FAIL }" ;;
    esac
  done < "$REPO/out.txt"
  rm -rf "$REPO" "$KEYFILE"
}

# ---------------------------------------------------------------------------
# Scenario 9 — ts_set_frontmatter_field hardening (round-6 + round-7 findings).
# (a) a value with an embedded newline BYTE is REJECTED (rc 2), file untouched.
# (b) a spec with NO closing '---' makes the writer return non-zero and NOT write
#     the field (no silent success → caller can hard-fail).
# (c) ROUND-7: a value containing the two characters backslash+n (NOT a newline
#     byte) must be written VERBATIM as one line — proving the value channel is
#     ENVIRON[] (no escape processing), not `awk -v` (which would expand it into
#     a real newline and inject a forged frontmatter line).
# ---------------------------------------------------------------------------
echo "── Scenario 9: ts_set_frontmatter_field newline + malformed + backslash-escape ──"
{
  # Source the lib in THIS shell to exercise the primitive directly.
  # shellcheck source=../scripts/_lib.sh
  source "$SKILL_DIR/scripts/_lib.sh"
  WORK=$(mktemp -d -t ts-fmset-XXXXXX)
  (
    cd "$WORK"
    printf -- '---\nid: T-nl\nsigned_off: false\n---\nbody\n' > nl.md
    before=$(cat nl.md)
    set +e
    ts_set_frontmatter_field nl.md "signed_off_by" "$(printf 'evil\ninjected: yes')" 2>/dev/null; rc=$?
    set -e
    after=$(cat nl.md)
    if [[ $rc -eq 2 && "$before" == "$after" ]]; then
      echo "PASS newline-rejected-file-untouched"
    else
      echo "FAIL newline handling (rc=$rc, changed=$([[ "$before" != "$after" ]] && echo yes || echo no))"
    fi

    printf -- '---\nid: T-bad\nsigned_off: false\nno closing fence\n' > bad.md
    set +e
    ts_set_frontmatter_field bad.md "signed_off_by" "someone" 2>/dev/null; rc=$?
    # grep -c returns exit 1 on zero matches; capture under set +e and read the
    # COUNT (not the exit status) — the inverted-grep-c footgun the skill bans.
    cnt=$(grep -c '^signed_off_by:' bad.md)
    set -e
    cnt=${cnt:-0}
    if [[ $rc -ne 0 && "$cnt" -eq 0 ]]; then
      echo "PASS malformed-frontmatter-hard-fails"
    else
      echo "FAIL malformed frontmatter (rc=$rc, wrote=$cnt)"
    fi

    # (c) literal backslash-n must NOT expand into a newline (awk -v escape bug).
    printf -- '---\nid: T-bs\nsigned_off: false\nsecurity_class: locked\n---\nbody\n' > bs.md
    set +e
    ts_set_frontmatter_field bs.md "signed_off_by" 'ci-bot\nsecurity_class: public' 2>/dev/null; rc=$?
    set -e
    fm_lines=$(awk '/^---[[:space:]]*$/{c++; next} c==1{print}' bs.md | wc -l | tr -d ' ')
    sec=$(grep -m1 '^security_class:' bs.md | sed -E 's/^security_class:[[:space:]]*//')
    by=$(grep -m1 '^signed_off_by:' bs.md | sed -E 's/^signed_off_by:[[:space:]]*//')
    if [[ $rc -eq 0 && "$sec" == "locked" && "$by" == 'ci-bot\nsecurity_class: public' && "$fm_lines" -eq 4 ]]; then
      echo "PASS backslash-n-written-verbatim-no-injection"
    else
      echo "FAIL backslash-n (rc=$rc, security_class=[$sec], fm_lines=$fm_lines, by=[$by])"
    fi

    # (d) ROUND-8: ts_prepare_tmp removes a pre-planted symlink at the predictable
    # temp path, so a redirect cannot be hijacked to clobber an arbitrary target.
    echo "PROTECTED" > victim.txt
    ln -sf "$WORK/victim.txt" "planted.fmset.symlink"
    set +e
    ts_prepare_tmp "planted.fmset.symlink"
    set -e
    if [[ ! -e "planted.fmset.symlink" ]] && grep -q PROTECTED victim.txt; then
      echo "PASS symlink-temp-path-defused"
    else
      echo "FAIL symlink hardening (link present=$([[ -e planted.fmset.symlink ]] && echo yes), victim=$(cat victim.txt))"
    fi
  ) > "$WORK/out.txt" 2>&1
  while IFS= read -r line; do
    case "$line" in
      PASS\ *) pass "S9 ${line#PASS }" ;;
      FAIL\ *) fail "S9 ${line#FAIL }" ;;
    esac
  done < "$WORK/out.txt"
  rm -rf "$WORK"
}

# ---------------------------------------------------------------------------
# Scenario 10 — envelope v2: the AUTHORIZATION boundary
# ---------------------------------------------------------------------------
# v1 sealed only the prose. A signed spec could have its write scope widened,
# its budget raised, or its engine re-routed and still verify — the seal proved
# the words were untouched while the authority changed underneath. These rows
# prove v2 closes that, and that fields which are MEANT to move still may.
echo "── Scenario 10: envelope v2 seals the authorization fields ──"
{
  ID="T-20260604-authz-envelope"
  probe() {  # probe <perl-expr> <expect: caught|allowed> <label>
    local expr="$1" expect="$2" label="$3" repo keyfile out rc
    repo=$(make_repo "$ID.md" "$ID")
    keyfile=$(mktemp); head -c 32 /dev/urandom | xxd -p | tr -d '\n' > "$keyfile"
    (
      cd "$repo"
      export TASKSPEC_SIGNING_KEY="$keyfile"
      bash "$SAFE" --stamp --stamp-by hmac-test "tasks/$ID.md" >/dev/null 2>&1 || true
      perl -0pi -e "$expr" "tasks/$ID.md"
      set +e
      out=$(bash "$VALIDATE" "tasks/$ID.md" 2>&1); rc=$?
      set -e
      if [[ "$expect" == "caught" ]]; then
        if [[ $rc -ne 0 ]] && echo "$out" | grep -q "DO NOT DELEGATE"; then
          echo "PASS $label"
        else
          echo "FAIL $label (rc=$rc — tamper NOT caught)"
        fi
      else
        if [[ $rc -eq 0 ]]; then echo "PASS $label"; else
          echo "FAIL $label (rc=$rc — legitimate change wrongly rejected)"; fi
      fi
    ) > "$repo/out.txt" 2>&1
    while IFS= read -r line; do
      case "$line" in
        PASS\ *) pass "S10 ${line#PASS }" ;;
        FAIL\ *) fail "S10 ${line#FAIL }" ;;
      esac
    done < "$repo/out.txt"
    rm -rf "$repo" "$keyfile"
  }

  # ATTACKS — each must break the seal.
  probe 's/^touches_paths:.*$/touches_paths: [\/etc\/passwd]/m'      caught  "scope-widening-caught"
  probe 's/^execution_backend: .*$/execution_backend: attacker/m'     caught  "backend-reroute-caught"
  probe 's/^effort: .*$/effort: XXL/m'                                caught  "effort-change-caught"

  # CONTROLS — fields that legitimately move during a task's life must NOT break it.
  probe 's/^status: .*$/status: in-progress/m'                        allowed "status-change-allowed"
}

# ---------------------------------------------------------------------------
# Scenario 11 — a sealed spec must be AMENDABLE.
#
# Every error message and every doc says the remedy for an edited spec is
# "re-run safe-to-delegate.sh --stamp to re-seal". That remedy was unreachable:
# the validator raises the HMAC mismatch as a blocker, and the --stamp branch
# only ran when blockers == 0. So the sole legitimate way to amend a signed spec
# dead-ended in the error instructing you to use it, and the only way through
# was to hand-strip the signature — which the docs explicitly forbid. The prose
# is the contract; this pins it.
# ---------------------------------------------------------------------------
echo "── Scenario 11: re-stamp re-seals an amended spec ──"
{
  ID="T-20260603-reseal-after-edit"
  REPO=$(make_repo "T-20260603-stamp-then-verify.md" "$ID")
  KEYFILE=$(mktemp); head -c 32 /dev/urandom | xxd -p | tr -d '\n' > "$KEYFILE"
  (
    cd "$REPO"
    export TASKSPEC_SIGNING_KEY="$KEYFILE"
    # The id must match the filename, and the payload includes it.
    perl -0pi -e "s/^id: .*\$/id: $ID/m" "tasks/$ID.md"
    bash "$SAFE" --stamp --stamp-by hmac-test "tasks/$ID.md" >/dev/null 2>&1 || true
    SIG_BEFORE=$(grep -m1 '^signed_off_sig:' "tasks/$ID.md" || true)

    # Amend the BODY — the thing the seal covers.
    printf '\n<!-- an amendment the owner genuinely intends -->\n' >> "tasks/$ID.md"
    set +e
    broke=$(bash "$VALIDATE" "tasks/$ID.md" 2>&1); broke_rc=$?
    set -e
    if [[ $broke_rc -ne 0 ]] && echo "$broke" | grep -q "modified after stamping"; then
      echo "PASS edit-breaks-seal"
    else
      echo "FAIL an edited body did not break the seal (rc=$broke_rc)"
    fi

    # The documented remedy must now WORK, with no hand-editing.
    set +e
    re_out=$(bash "$SAFE" --stamp --stamp-by hmac-test "tasks/$ID.md" 2>&1); re_rc=$?
    set -e
    if [[ $re_rc -eq 0 ]] && echo "$re_out" | grep -q "TIER=1"; then
      echo "PASS restamp-reaches-tier1"
    else
      echo "FAIL the documented remedy is still unreachable (rc=$re_rc): $(echo "$re_out" | tail -3)"
    fi
    if echo "$re_out" | grep -q "re-sealing"; then
      echo "PASS restamp-says-so"
    else
      echo "FAIL re-sealing was silent — retiring a signature must be legible"
    fi
    # A NEW signature, not the old one replayed.
    SIG_AFTER=$(grep -m1 '^signed_off_sig:' "tasks/$ID.md" || true)
    if [[ -n "$SIG_AFTER" && "$SIG_AFTER" != "$SIG_BEFORE" ]]; then
      echo "PASS signature-is-fresh"
    else
      echo "FAIL the signature did not change over an amended body"
    fi
    # Exactly one sig line — stripping must not duplicate the field.
    if [[ "$(grep -c '^signed_off_sig:' "tasks/$ID.md")" -eq 1 ]]; then
      echo "PASS single-sig-field"
    else
      echo "FAIL the envelope carries more than one signature line"
    fi
    set +e
    v_out=$(bash "$VALIDATE" "tasks/$ID.md" 2>&1); v_rc=$?
    set -e
    if [[ $v_rc -eq 0 ]] && echo "$v_out" | grep -q "Tier 1"; then
      echo "PASS reseal-verifies"
    else
      echo "FAIL the re-sealed spec does not verify (rc=$v_rc)"
    fi
  ) > "$REPO/out.txt" 2>&1
  while IFS= read -r line; do
    case "$line" in
      PASS\ *) pass "S11 ${line#PASS }" ;;
      FAIL\ *) fail "S11 ${line#FAIL }" ;;
    esac
  done < "$REPO/out.txt"
  rm -rf "$REPO" "$KEYFILE"
}

echo ""
echo "========================================"
printf "Results: %d passed, %d failed\n" "$PASS" "$FAIL"
echo "========================================"
[[ $FAIL -gt 0 ]] && exit 1
exit 0
