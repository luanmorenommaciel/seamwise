# The `signed_off` autonomy contract

> **Confidence:** HIGH (load-bearing concept)
> **Audience:** Spec authors, agent implementers, supervisor authors
> **Related:** [agent-contract.md](agent-contract.md), [eval-driven-development.md](eval-driven-development.md), [task-spec-v1.md](task-spec-v1.md), [../patterns/runnable-bash-evals.md](../patterns/runnable-bash-evals.md)

---

## One sentence

`signed_off: true` is the durable, file-resident attestation that this Task-Spec passed the structural validator AND the eval execution gate at a specific point in time — meaning an autonomous engine (Kimi, Codex, Claude) is permitted to crank it unsupervised.

---

## Who can produce it

**Only one script:** `scripts/safe-to-delegate.sh --stamp <spec>`.

The script flips `signed_off:` from `false` to `true` in the YAML frontmatter, stamps `signed_off_by:` with the author's identity (default `$USER`, override with `--stamp-by`), and records `signed_off_at:` with an ISO-8601 timestamp.

It does this only after BOTH of the following pass:

1. **Structural validation** — `validate-task-spec.sh` exits 0 on the spec (all required frontmatter fields, all 6 zones, no leftover `{{TODO}}` placeholders, eval functions defined, Exit Check covers every `eval_N`).
2. **Eval execution gate** — the bash eval bodies extracted from the Success Criteria and Exit Check sections run in an isolated subshell without bash-level errors (no `syntax error`, no `unbound variable`, no `command not found`, no inverted-count footguns). Per the gate's design, **assertion failures are expected** on an unbuilt task — the work isn't done yet. What's blocked is the spec being broken bash on its own terms.

If either check fails, the gate refuses to stamp. The spec remains `signed_off: false`.

---

## Who CANNOT produce it

**Humans editing the YAML by hand.** **Agents writing the YAML programmatically.** **Any script other than `safe-to-delegate.sh`.**

The `validate-task-spec.sh` linter enforces this with the **sign-off envelope** check (Check 17). There are two layers:

1. **Structural floor (always on):** a `signed_off: true` field without both a non-empty `signed_off_by` and an ISO-8601 `signed_off_at` is a structural error. The spec fails validate. This catches *accidental* hand-stamping.
2. **HMAC envelope (key-optional, v2.2):** when a signing key is present, `safe-to-delegate.sh --stamp` also seals a `signed_off_sig: hmac-sha256-v1:<keyid>:<hex>` line, and the verifier recomputes the MAC. This catches *adversarial* post-stamp modification of the body or the envelope values.

This is the autonomy boundary. Hand-stamping defeats the entire purpose: the whole point of `signed_off` is that downstream supervisors can trust the bit without re-running the gate themselves.

### What the HMAC envelope IS and IS NOT (v2.2 — crypto is HERE)

As of v2.2 the sign-off envelope carries a real cryptographic MAC. Be precise about what that buys and what it does not:

- **What it IS:** a keyed HMAC-SHA256 over a canonical payload — the spec's `id`, the `body_digest` (sha256 of everything after the closing frontmatter `---`), and the three `signed_off*` values. Sealed by `safe-to-delegate.sh --stamp`, re-verified by `validate-task-spec.sh`. Any edit to the spec body, or to `signed_off`/`signed_off_by`/`signed_off_at`, after stamping changes the payload and the MAC no longer matches — the verifier hard-fails. This defeats the forgery the v2.1.1 structural check could not: a co-author who reads this skill, learns the envelope shape, and hand-edits `signed_off_by: luan` cannot produce a matching MAC without the key.
- **What it IS NOT — symmetric, not non-repudiation:** HMAC is a *symmetric* primitive. The key is shared across the repo. Anyone who can read the key (every developer with the clone, every CI signer) can forge a valid stamp. So the envelope binds **"a repo-key holder stamped this"**, NOT **"Luan specifically stamped this."** Per-author non-repudiation — proving *which* individual signed — requires asymmetric signatures (e.g. Ed25519 / DSSE with per-author keys). That is a deliberate, named future hardening, not part of this contract.
- **The threat model:** the adversary is an **adversarial co-author who read the skill** and tries to hand-forge an autonomy stamp, or an accidental post-stamp edit that silently invalidates the work. It is NOT a remote supply-chain attacker who has already compromised the machine and read the key — against that adversary a shared symmetric key offers nothing, and we do not claim otherwise.
- **Key-optional by design:** a fresh clone, a CI image with no key, or a container with no `openssl`/`shasum`/`sha256sum` must still be usable. With no key (or no crypto binary) the envelope degrades to **structural-only (Tier 2)** — it never hard-fails *shut* merely because the key is absent. See "The three tiers" below.

See [`tests/fixtures/T-20260603-fake-envelope.md`](../../tests/fixtures/T-20260603-fake-envelope.md) for the honest no-key fixture: with no key it is accepted at Tier 2 (the forgery is invisible without crypto). The keyed Tier-1/Tier-3 behaviour — stamp-then-verify and tamper-detection — is proven in [`tests/test-hmac-envelope.sh`](../../tests/test-hmac-envelope.sh) against [`T-20260603-stamp-then-verify.md`](../../tests/fixtures/T-20260603-stamp-then-verify.md) and [`T-20260603-tampered-body.md`](../../tests/fixtures/T-20260603-tampered-body.md).

### The three tiers

`validate-task-spec.sh` Check 17 degrades on the presence of a key and a signature:

| Tier | Condition | Verdict | Dispatch eligibility |
|------|-----------|---------|----------------------|
| **Tier 1** | key present + `signed_off_sig` present + MAC verifies | full crypto trust, exit 0 | unsupervised crank OK |
| **Tier 2** | key MISSING (fresh clone / no env var / no crypto binary) OR `signed_off_sig` absent (legacy v2.1.1 spec) | structural-only, **LOUD warning**, exit 0 | **supervised dispatch ONLY** |
| **Tier 3** | key present but MAC MISMATCH, or `signed_off_sig` malformed | hard FAIL, exit 1: "DO NOT DELEGATE: spec body or envelope modified after stamping" | refuse |

Tier 2 NEVER hard-fails just because there is no key — that would make the skill unusable on any fresh clone. But it is not free: see the policy below.

### Tier-2 policy — supervised dispatch only (MANDATORY)

**A Tier-2 sign-off is NOT dispatch-eligible for unsupervised crank.** It permits read / inspect / triage only. A human must supervise any dispatch of a Tier-2 spec.

This closes the **downgrade-bypass** hole: without this rule, an adversary who read the skill could simply run the verifier *without* the key, reach the (forgeable) Tier-2 state, and dispatch unsupervised. The policy makes the absence of crypto a supervision requirement, not a green light. To reach unsupervised-dispatch trust (Tier 1), provision a key — `configs/setup-taskspec-signing-key.sh` — and re-stamp with `safe-to-delegate.sh --stamp`.

`safe-to-delegate.sh` surfaces the tier in its VERDICT block: a Tier-2 spec prints `sign-off: structural-only (Tier 2) — supervised dispatch only`.

---

## What it asserts

Three claims, in order of importance:

1. **The evals are well-formed bash.** They don't error on syntax, undefined vars, missing commands, or known anti-patterns (inverted `grep -c`, etc.). When the executor runs them, they'll fail for the RIGHT reason ("assertion not yet true") rather than the WRONG reason ("the eval is broken").
2. **The structural contract holds.** Every required field exists. The id matches the filename. `touches_paths` and `depends_on` resolve. The Exit Check references every defined `eval_N`. The validation card schema is intact.
3. **An author with name X attested to this at time T.** The `signed_off_by` + `signed_off_at` fields are the audit trail. They tell a supervisor *who* claimed responsibility and *when*. If the spec is later found defective, the gate's verdict is the artifact.

What it does **not** assert: that the work has been done. A `signed_off: true` spec with `status: ready` has not been executed yet — it's simply safe to hand off to an engine. The engine flips status to `in-progress` → `done` (or `parked`) during execution.

---

## Why validate-task-spec.sh is NOT the gate

`validate-task-spec.sh` is the **pre-gate linter**. It checks the structural contract but not the eval execution behaviour. A spec that passes `validate-task-spec.sh` can still:

- Contain bash evals that error on every run (e.g. `[ "0\n0" -eq 0 ]` due to the inverted-grep-c footgun)
- Have `eval_N` defined but never referenced in the Exit Check
- Carry a fake `signed_off: true` hand-stamped by an over-eager author

Stopping at `validate` was the failure mode the ADF Decimal pilot exposed: the author stamped, the engine ran, the evals reported FAIL when the work was actually COMPLETE. The gate (`safe-to-delegate.sh`) catches that class; the linter does not.

The contract:

| Script | Role | Failure mode it catches |
|--------|------|-------------------------|
| `validate-task-spec.sh` | Structural linter (pre-gate) | Missing fields, malformed YAML, leftover `{{TODO}}`, inverted-count anti-patterns |
| `safe-to-delegate.sh --stamp` | The gate (the only stamper) | Eval bodies that error on execution; mismatch between structural pass and runtime behaviour |
| `safe-to-delegate.sh` (no `--stamp`) | The gate (dry-run verdict) | Same checks; reports DELEGATE / DO NOT DELEGATE without modifying the file |

**Do not hand-stamp `signed_off`.** If you find yourself wanting to, the answer is "fix the spec so the gate accepts it."

---

## What happens if the gate fails

Three failure classes:

1. **Structural failure** (validate exits non-zero). The gate reports `DO NOT DELEGATE` and lists the structural errors. Fix the spec; re-run.
2. **Broken-eval failure** (eval body errors on execution — syntax, unbound var, command-not-found, integer-comparison-against-non-integer). The gate reports `DO NOT DELEGATE` and surfaces the offending eval. Fix the eval (see [../patterns/runnable-bash-evals.md](../patterns/runnable-bash-evals.md) for the canonical patterns); re-run.
3. **HMAC envelope failure (Tier 3)** — a key is present but the `signed_off_sig` MAC does not match, or the sig field is malformed. This means the spec body or an envelope value was modified after stamping. The verifier hard-fails with "DO NOT DELEGATE: spec body or envelope modified after stamping". The fix is to re-run `safe-to-delegate.sh --stamp` to re-seal the (now-current) spec — never to hand-edit the sig.

In the first two cases the spec remains `signed_off: false`. In the Tier-3 case the spec is `signed_off: true` but no longer trustworthy; treat it as tampered until re-stamped. In all cases the supervisor (Claude Code, taskship, anthive, etc.) will refuse to dispatch it.

---

## See also

- [agent-contract.md](agent-contract.md) — the cross-vendor contract every spec carries; includes the v2.1 machine schema with `signed_off` semantics
- [eval-driven-development.md](eval-driven-development.md) — why runnable bash evals are the moat
- [../patterns/runnable-bash-evals.md](../patterns/runnable-bash-evals.md) — common foot-guns including inverted `grep -c`
- [../../runbooks/dispatching-a-task-spec.md](../../runbooks/dispatching-a-task-spec.md) — what to do AFTER you stamp (includes the Tier-2 supervised-only rule)
- [../../runbooks/validating-a-task-spec.md](../../runbooks/validating-a-task-spec.md) — what `validate-task-spec.sh` checks (the pre-gate)
- [../../configs/setup-taskspec-signing-key.sh](../../configs/setup-taskspec-signing-key.sh) — provision the repo signing key to reach Tier 1
- [../../tests/test-hmac-envelope.sh](../../tests/test-hmac-envelope.sh) — keyed Tier-1/2/3 regression suite for the HMAC envelope
