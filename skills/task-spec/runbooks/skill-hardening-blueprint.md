# Skill-Hardening Blueprint — driving a skill to a 9+ sign-off

> The reproducible process used to take the task-spec skill from a rated 8.5 (v2.1.1)
> to a converged 9.0–9.5 (v2.2). This is the **blueprint for hardening the other skills**:
> a research → build → adversarial-loop → converge → sign-off pipeline, with the exact
> gates, roles, and stop conditions that made it work.

This document is process, not feature. It explains *how* the skill reached sign-off so the
same path can be re-run on the next skill without re-deriving it.

---

## The shape of the work

```
 ┌─ Phase 0 ─────────┐   ┌─ Phase 1 ─────┐   ┌─ Phase 2 (the loop) ──────────────────┐   ┌─ Phase 3 ──┐
 │ RESEARCH (MCP)    │ → │ BUILD          │ → │  REVIEW → FIX → RE-VERIFY  (repeat)    │ → │ SIGN-OFF   │
 │ find SOTA + the   │   │ smallest units │   │  adversary runs the code, default     │   │ converged? │
 │ adversarial traps │   │ each w/ tests  │   │  to REFUTE; fix; re-run ALL gates      │   │ merge      │
 └───────────────────┘   └────────────────┘   └───────────────────────────────────────┘   └────────────┘
        │                        │                          │                                    │
   Exa/Context7/Ref        one commit per unit       one commit per round                 blueprint + tag
```

The engine of quality is **Phase 2**, and its discipline is the whole point: you do not stop
after one review. You loop until a review round comes back with **no material finding** —
that is the definition of *converged*. A first review that finds nothing usually means the
review was shallow, not that the code was perfect.

---

## Phase 0 — Research (MCP-grounded, adversarial up front)

Before building, use the MCP tools (Exa `web_search_exa` / `get_code_context_exa`,
Context7 `query-docs`, Ref `ref_search_documentation`) to find the **state of the art** AND,
more importantly, the **adversarial traps** the SOTA already knows about. For the sign-off
envelope this surfaced three traps that were then designed-out *before* writing code:

- crypto must be **key-optional** (no hard openssl dependency → degrade to a structural tier)
- the signed payload boundary must **exclude the signature line itself** (or it self-invalidates)
- a downgrade path (run the verifier without the key) must be **blocked**, not just documented

Output of Phase 0: a short list of "things a naive build would get wrong," each of which
becomes a guard baked into Phase 1.

---

## Phase 1 — Build in smallest revertable units

Decompose into units that each (a) do one thing, (b) ship their own regression test, and
(c) are independently revertable. For v2.2 these were B0 (bash-3.2 guard), B1 (conformance
driver), B2 (HMAC envelope), B3 (cross-engine proof). One commit per unit. Run the full gate
suite after each — a unit isn't done until every gate is green on the **portability floor**
(here: macOS system bash 3.2.57, not just the dev bash 5).

---

## Phase 2 — The adversarial loop (the part that actually creates quality)

Each round has three steps, and a round is not over until step 3 is green.

### Step 1 — REVIEW: an adversary that RUNS the code

Dispatch an adversarial reviewer with a prompt that forces it to **execute**, not reason:

- "You are an adversary. **Default to refute.** Do NOT trust 'all green' claims — RUN it."
- Give it concrete attack vectors (escape sequences, injection payloads, malformed input,
  the portability floor, concurrent access, symlink TOCTOU).
- Require **per-finding reproduction commands** and an explicit list of *which* areas it
  actually ran vs only reasoned about.
- Demand a verdict: `SIGN-OFF READY at 9+` | `BLOCKERS REMAIN`, with a rating.

Reviewer routing (in priority order — use whichever is available):
1. `/codex:review` and `/codex:adversarial-review` (the `codex:codex-rescue` subagent).
2. If Codex is unavailable, a **general-purpose agent** with the same run-the-code prompt.
   This is not a fallback of last resort — across these rounds it found real HIGH bugs that
   a reasoning-only review would have missed, because it reproduced them.

### Step 2 — FIX: reproduce first, then fix, then add a regression

Non-negotiable order for every finding:
1. **Reproduce it yourself** before fixing. (Twice here the reviewer's severity was slightly
   off — BSD vs GNU awk semantics — but reproducing revealed the *correct* fix regardless.)
2. Fix with the **smallest change** that closes the class, not just the instance. (The sed
   injection wasn't patched character-by-character — the value channel was moved off `sed`
   to one injection-safe primitive, then off `awk -v` to `ENVIRON[]`.)
3. **Add a regression test** that fails without the fix and passes with it. The reviewer's
   attack inputs become permanent assertions (Scenario 7/8/9 in `test-hmac-envelope.sh`).

### Step 3 — RE-VERIFY: all gates, both bash versions, plus static analysis

Re-run **every** gate (not just the one you touched) on the portability floor *and* the dev
bash. Run `shellcheck -S warning` on edited scripts — it caught a real dead branch (SC2320)
in a fix during these rounds. A round is done only when all gates are green and shellcheck is
clean on the lines you touched.

### Re-review the FIX, not just the original

The highest-value rounds here reviewed the **previous round's fix**: R6 found that the R5
injection fix had two silent-failure edges; R7 found the R6 fix had an escape-expansion hole.
A fix to a security-sensitive path is itself new attack surface — always send it back through
Step 1.

---

## Phase 3 — Convergence and sign-off

### The convergence signal

You are converged when severity **monotonically declines** across independent rounds and a
fix **survives the next round's attack**. The v2.2 trajectory:

| Round | Findings | Severity |
|-------|----------|----------|
| 4 | sed-injection + 3 | 1 HIGH |
| 6 | 2 silent-failure edges in the R5 fix | 2 BLOCKING |
| 7 | awk -v escape-expansion + conformance fail-open | 1 HIGH (narrower) + 1 LOW |
| 8 | temp-file symlink TOCTOU | **1 LOW — verdict CONVERGED** |

The v2.2.1 follow-up (9.0 → 9.5) hardened the eval-runner surface:

| Round          | Findings                                                                  | Severity                                  |
|----------------|---------------------------------------------------------------------------|-------------------------------------------|
| 9 (stdin)      | eval runner inherits caller stdin → `read`-in-eval HANGS the gate         | 1 HIGH (reachable, proven RC=137)         |
| 9b (re-review) | first fix left the Exit Check runner unguarded; (C) test over-claimed it  | 1 MED + 1 honesty fix — **CONVERGED**     |

"Zero findings on round 1" is not convergence — it is an under-powered review. "Each round
finds less, and only outside the documented threat model" is convergence. Round 9 is the
canonical example of the re-review rule paying off: the round that reviewed the round-9 *fix*
caught both an incomplete patch and a test that asserted a property without proving it
load-bearing — neither visible from a green test run alone.

### The sign-off gate

Sign-off requires ALL of:
- every gate green on the **portability floor** and the dev bash;
- `shellcheck` clean on every edited script;
- a review round whose only findings are LOW and outside the documented threat model
  (or none), with the reviewer stating plainly it **tried to break it and could not**;
- every accepted finding closed with a **regression test**;
- the CHANGELOG and version string consistent (the skill's own doc-lint enforces this).

### Merge

One revertable commit per round, descriptive messages citing the finding and its repro,
then merge the branch. Develop the whole loop in an **isolated worktree** so a long
adversarial loop never destabilizes the main checkout.

---

## What made the difference (carry these to the next skill)

1. **The reviewer must run the code.** Every real bug here was in the *plumbing* (how
   untrusted bytes flow through `sed` / `awk -v` / shell redirects), invisible to a
   reasoning-only pass. The crypto *math* was never wrong.
2. **Reproduce before fixing.** It corrects the reviewer's mistakes and proves the fix.
3. **Re-review the fix.** A security fix is new attack surface.
4. **Test on the portability floor.** The conformance suite was *silently* no-op'ing on
   macOS bash 3.2 (`mapfile` not found) while green on bash 5 — found only by running 3.2.
5. **Smallest-class fix, not instance fix.** Move the unsafe channel; don't escape one char.
6. **Convergence is a trend, not an event.** Loop until severity bottoms out at
   below-threshold; let the trend — not a single clean review — authorize sign-off.
7. **Dogfood the skill's own rules.** A test here tripped the very `grep -c` footgun the
   skill bans; the skill must follow its own published rules everywhere.

---

## References

- Agent: this loop is engine-agnostic — any adversarial reviewer that runs the code works.
- Template: `runbooks/validating-a-task-spec.md` (the per-spec gate this scales up from).
- Contracts: `references/concepts/agent-contract.md` (RFC-2119 + conformance suite).
- Next Step: re-run Phase 0→3 on the next skill; reuse this file as the checklist.
